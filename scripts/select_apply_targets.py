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
    "greenhouse.io":            "greenhouse",
    "job-boards.greenhouse.io": "greenhouse",
    "boards.greenhouse.io":     "greenhouse",
    "job-boards.eu.greenhouse.io": "greenhouse",
    "boards.eu.greenhouse.io":  "greenhouse",
    "jobs.ashbyhq.com":         "ashby",
    "ashbyhq.com":              "ashby",
    "jobs.lever.co":            "lever",
    "lever.co":                 "lever",
    "workable.com":             "workable",
    "apply.workable.com":       "workable",
    "jobs.workable.com":        "workable",
    "smartrecruiters.com":      "smartrecruiters",
    "jobs.smartrecruiters.com": "smartrecruiters",
}
# Hard-excluded from /apply picks. Verified 2026-07-15: LinkedIn URLs hit 2FA
# login walls in the MCP Chromium (5/5 skipped), Indeed pages have no external
# apply link (1/1 skipped), Workday/iCIMS are too brittle to auto-drive.
# These jobs stay visible in the dashboard UI — they're only excluded here.
# The crawler now resolves job_url_direct at crawl time, so any listing still
# carrying an aggregator URL has no known direct URL.
BLOCKED_ATS = {
    "linkedin.com":           "linkedin",
    "myworkdayjobs.com":      "workday",
    "workday.com":            "workday",
    "icims.com":              "icims",
    "indeed.com":             "indeed",
    "glassdoor.com":          "glassdoor",
    "ziprecruiter.com":       "ziprecruiter",
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


def normalize_url_for_dedup(u):
    """Strip trailing /application, /apply, query params, hash, trailing slash — for dedup only."""
    if not u: return ""
    u = u.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    for tail in ("/application", "/apply", "/apply-online", "/applications/new"):
        if u.lower().endswith(tail):
            u = u[: -len(tail)].rstrip("/")
            break
    return u.lower()


def normalize_title_for_dedup(t):
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


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

    candidates, skipped_ats_stats, skipped_below_score, skipped_applied = [], {}, 0, 0
    for j in session.get("jobs", []):
        ats = classify_url(j.get("url"))
        skipped_ats_stats.setdefault(ats or "no-url", 0)
        skipped_ats_stats[ats or "no-url"] += 1

        if ats is None or ats.startswith("BLOCKED:"):
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

        candidates.append({
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
            "ats_at_url": ats,  # what the URL host looked like; sub-agent may find a different landing
        })

    # Sort: supported ATS first (score desc), then unsupported (custom career
    # sites — sub-agent makes a best-effort pass). Aggregators never get here.
    def tier(c):
        a = c.get("ats_at_url") or "no-url"
        return 2 if a in ("no-url", "unsupported") else 1
    candidates.sort(key=lambda x: (tier(x), -(x["score"] or 0)))

    # Dedup by normalized URL AND by (company, normalized-title) — catches Ashby /application
    # variants and cross-source reposts (e.g. Jobgether wrapping a Quora Ashby URL).
    seen_urls, seen_title_company, deduped = set(), set(), []
    dropped_dupes = 0
    for c in candidates:
        nu = normalize_url_for_dedup(c["url"])
        tc = ((c.get("company") or "").lower().strip(), normalize_title_for_dedup(c.get("title")))
        if nu in seen_urls or tc in seen_title_company:
            dropped_dupes += 1
            continue
        seen_urls.add(nu); seen_title_company.add(tc)
        deduped.append(c)

    if args.top_n:
        cut = args.top_n
    else:
        cut = max(1, int(round(len(deduped) * args.top_percent / 100)))
    picked = deduped[:cut]

    out = {
        "session_id":   session["id"],
        "session_date": session["date"],
        "session_window": session["window"],
        "session_total_surfaced": len(session.get("jobs", [])),
        "eligible_after_filters": len(candidates),
        "unique_after_dedup": len(deduped),
        "dupes_dropped": dropped_dupes,
        "picked_count": len(picked),
        "min_score_floor": args.min_score,
        "top_percent": args.top_percent,
        "ats_distribution": skipped_ats_stats,
        "skipped_below_score": skipped_below_score,
        "skipped_already_applied": skipped_applied,
        "targets": picked,
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
