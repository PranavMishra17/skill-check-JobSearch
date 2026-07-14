"""select_apply_targets.py — pick which jobs /apply should attempt.

Reads jobs_ui/data.js (the latest session), filters to:
  - not already applied (companies in state.applied_or_tracking)
  - not already attempted (job_ids in state.applied_ids)
  - ATS in the supported allowlist
Sorts by score descending, cuts to top-percentile or top-N.
Emits a JSON list to stdout for /apply to consume.

Usage:
    python select_apply_targets.py \\
        --data jobs_ui/data.js \\
        --state ~/.job_search/state.json \\
        --top-percent 25 \\
        --min-score 60
"""
import argparse, json, os, re, sys, hashlib
from pathlib import Path

# --- ATS allowlist. Everything else is skipped.
# Workday and iCIMS excluded — too brittle to auto-apply reliably.
# LinkedIn excluded — aggressive bot detection.
SUPPORTED_ATS = {
    "greenhouse.io":     "greenhouse",
    "job-boards.greenhouse.io": "greenhouse",
    "boards.greenhouse.io": "greenhouse",
    "jobs.ashbyhq.com":  "ashby",
    "ashbyhq.com":       "ashby",
    "jobs.lever.co":     "lever",
    "lever.co":          "lever",
    "workable.com":      "workable",
    "apply.workable.com":"workable",
    "jobs.workable.com": "workable",
    "smartrecruiters.com": "smartrecruiters",
    "jobs.smartrecruiters.com": "smartrecruiters",
}
BLOCKED_ATS = {
    "linkedin.com":           "linkedin",
    "myworkdayjobs.com":      "workday",
    "workday.com":            "workday",
    "icims.com":              "icims",
    "indeed.com":             "indeed",  # Indeed apply is inconsistent; skip
}


def classify_url(url):
    if not url: return None
    host = re.search(r"https?://([^/]+)", url)
    if not host: return None
    domain = host.group(1).lower()
    for pat, ats in SUPPORTED_ATS.items():
        if pat in domain:
            return ats
    for pat, ats in BLOCKED_ATS.items():
        if pat in domain:
            return f"BLOCKED:{ats}"
    return "unsupported"


def parse_data_js(path):
    txt = Path(path).read_text(encoding="utf-8")
    m = re.search(r"window\.JOB_SESSIONS\s*=\s*(.*?);?\s*$", txt, flags=re.S)
    if not m:
        return []
    return json.loads(m.group(1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data",  default="jobs_ui/data.js")
    ap.add_argument("--state", default=os.path.expanduser("~/.job_search/state.json"))
    ap.add_argument("--session-id", default=None,
                    help="Specific session id to pull from. Defaults to newest.")
    ap.add_argument("--top-percent", type=int, default=25,
                    help="Take top N%% by score (default 25 → top quartile).")
    ap.add_argument("--top-n", type=int, default=None,
                    help="Optional absolute cap. If set, min(top-N, top-percent).")
    ap.add_argument("--min-score", type=int, default=60,
                    help="Absolute score floor (default 60).")
    args = ap.parse_args()

    sessions = parse_data_js(args.data)
    if not sessions:
        print(json.dumps({"error": "no sessions in data.js"}))
        sys.exit(1)
    session = next((s for s in sessions if s["id"] == args.session_id), sessions[0])

    state = json.loads(Path(os.path.expanduser(args.state)).read_text(encoding="utf-8"))
    applied_companies = {c.lower() for c in state.get("preferences", {}).get("applied_or_tracking", [])}
    already_attempted = set(state.get("applied_ids", []))  # created lazily by /apply

    supported, skipped_by_ats, skipped_below_score, skipped_applied = [], {}, 0, 0
    for j in session.get("jobs", []):
        ats = classify_url(j.get("url"))
        if ats is None or ats == "unsupported" or ats.startswith("BLOCKED:"):
            skipped_by_ats.setdefault(ats or "no-url", 0)
            skipped_by_ats[ats or "no-url"] += 1
            continue
        if j.get("score", 0) < args.min_score:
            skipped_below_score += 1
            continue
        company = (j.get("company") or "").strip().lower()
        if company and company in applied_companies:
            skipped_applied += 1; continue
        # Recompute stable id for state matching
        jid = hashlib.sha256(
            f"{company}{(j.get('title') or '').lower()}{j.get('url') or ''}".encode()
        ).hexdigest()[:16]
        if jid in already_attempted:
            skipped_applied += 1; continue

        supported.append({
            "job_id": jid,
            "rank": j.get("rank"),
            "score": j.get("score"),
            "title": j.get("title"),
            "company": j.get("company"),
            "url": j.get("url"),
            "location": j.get("location"),
            "arrangement": j.get("arrangement"),
            "salary": j.get("salary"),
            "posted": j.get("posted"),
            "description": j.get("description"),
            "ats": ats,
        })

    supported.sort(key=lambda x: -(x["score"] or 0))
    # If --top-n is set, it is the primary cut (absolute count).
    # Otherwise fall back to --top-percent of the supported list.
    if args.top_n:
        cut = args.top_n
    else:
        cut = max(1, int(round(len(supported) * args.top_percent / 100)))
    picked = supported[:cut]

    out = {
        "session_id":   session["id"],
        "session_date": session["date"],
        "session_window": session["window"],
        "session_total_surfaced": len(session.get("jobs", [])),
        "supported_in_session": len(supported),
        "picked_count": len(picked),
        "min_score_floor": args.min_score,
        "top_percent": args.top_percent,
        "skipped_by_ats": skipped_by_ats,
        "skipped_below_score": skipped_below_score,
        "skipped_already_applied": skipped_applied,
        "targets": picked,
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
