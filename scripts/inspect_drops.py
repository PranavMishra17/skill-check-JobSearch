"""inspect_drops.py — show what render_results.py filtered out and why.

Re-runs the same filters as render_results.py on a raw dataset, but instead of
writing a session, it groups the drops by reason and prints sample items per
bucket so we can audit false positives.

Usage:
    python inspect_drops.py --dataset <path> --window-days 3
"""
import argparse, json, os, re, sys, hashlib, datetime
from collections import defaultdict

# Same filter logic as render_results.py
NO_SPONSOR_PATS = [
    r"must be (?:legally )?(?:authoriz(?:ed)?|allowed) to work in the (?:us|u\.s\.|united states)(?: without (?:visa )?sponsorship)?",
    r"without (?:visa )?sponsorship now or in the future",
    r"unable to (?:offer|provide|sponsor)",
    r"do not (?:offer|provide|sponsor)",
    r"we (?:do not|don't|cannot|can't) sponsor",
    r"no (?:visa )?sponsorship (?:available|provided|offered)",
    r"not (?:able|currently able|in a position) to (?:offer )?sponsor",
    r"ineligible for sponsorship",
    r"this position is not eligible for (?:visa )?sponsorship",
    r"unable to consider applicants requiring",
    r"this role (?:does not|will not) (?:offer|provide) sponsorship",
    r"sponsorship is not available",
]
CITIZENSHIP_PATS = [
    r"\bus citizenship\b", r"\bu\.s\. citizenship\b",
    r"must be a us citizen", r"must be a u\.s\. citizen",
    r"\bts/sci\b", r"\btop secret\b", r"\bsecret clearance\b",
    r"active clearance", r"security clearance",
    r"us citizens? or green card holders? only",
    r"green card holders? only", r"only.{0,30}u\.s\. citizens",
]
TITLE_SENIOR_DROP = re.compile(
    r"\b(senior|sr\.?|lead|staff|principal|manager|director|vp|head\s+of|sr\s+staff|chief)\b", re.I)
PURE_FRONTEND = re.compile(r"\bfront.?end (developer|engineer)\b|\bui developer\b|\breact developer\b", re.I)
YOE_RE = re.compile(r"\b(\d{1,2})\+?\s*(?:to|–|-)?\s*\d{0,2}\s*(?:\+)?\s*years?\b(?!\s+experience\s+is\s+preferred)", re.I)
TITLE_SCOPE = [
    "ai engineer", "ml engineer", "machine learning engineer", "llm engineer",
    "founding engineer", "forward deployed", "forward-deployed",
    "applied ai", "applied scientist", "applied ml",
    "research scientist",  # "research engineer" removed 2026-06-09
    "ai/ml", "ai engineering", "software engineer", "software developer",
    "ai infrastructure", "ml infrastructure", "platform engineer",
    "ai researcher", "ml researcher", "deep learning engineer",
    "ai platform", "ml platform", "ai systems", "ai associate",  # "data scientist" removed 2026-06-09
    "computer scientist", "generative ai",
    "agentic", "ai agent", "agent engineer", "agentic engineer", "agentic ai",
    "vibe coder", "vibe coding", "vibe engineer",
    "claude developer", "claude engineer", "gpt developer", "gpt engineer",
    "llm developer", "llm tooling", "llm ops", "llmops", "mlops",
    "prompt engineer", "prompt architect",
    "ai builder", "ai developer", "ai automation", "ai integration",
    "ai solutions engineer", "ai solutions architect", "ai tooling",
    "ai product engineer", "ai workflow",
    "langchain", "langgraph", "copilot engineer", "cursor engineer",
    "rag engineer", "retrieval engineer",
    "ai research",
]
COMPANY_EXCLUDE = {"alfred_", "alfred"}


def any_re(text, pats):
    return text and any(re.search(p, text, re.I) for p in pats)


def has_high_yoe(desc):
    if not desc: return False
    for m in YOE_RE.finditer(desc[:4000]):
        try: years = int(m.group(1))
        except: continue
        if years >= 4:
            window = desc[max(0, m.start()-80):m.end()+80].lower()
            if re.search(r"(experience|required|minimum|at least|must have|preferred)", window):
                return True
    return False


def days_since(ds, today):
    if not ds: return 999
    try:
        return (today - datetime.datetime.fromisoformat(ds.replace("Z","+00:00")).date()).days
    except: return 999


def should_drop(it, applied_lower, seen_ids, window_days, today):
    t = it.get("title") or ""
    org = (it.get("organization") or "").lower()
    desc = it.get("description_text") or ""
    countries = it.get("countries_derived") or []

    if not countries or not all("United States" in c for c in countries):
        return "non-US"
    if it.get("linkedin_org_recruitment_agency_derived") is True:
        return "agency"
    if org in COMPANY_EXCLUDE: return "current-employer"
    if org in applied_lower: return "already-applied"
    if not any(k in t.lower() for k in TITLE_SCOPE): return "title-out-of-scope"
    if TITLE_SENIOR_DROP.search(t): return "title-too-senior"
    if PURE_FRONTEND.search(t): return "pure-frontend"

    lvl = it.get("ai_experience_level")
    if lvl in ("5-10", "10+"): return f"ai-experience-level:{lvl}"
    if has_high_yoe(desc): return "yoe>=4-required"

    if any_re(desc, CITIZENSHIP_PATS): return "citizenship/clearance"
    tax = " ".join(it.get("ai_taxonomies_a") or []).lower()
    if "defense" in tax or "military" in tax: return "defense"
    if re.search(r"\b(department of (?:war|defense)|\bdod\b|military|national security)\b", desc, re.I):
        if any(w in (it.get("linkedin_org_description") or "").lower() for w in ["defense","military","intelligence","national security"]):
            return "defense-employer"

    if any_re(desc, NO_SPONSOR_PATS): return "no-sponsorship"
    if it.get("ai_visa_sponsorship") is False:
        if re.search(r"sponsor(?:ship)?", desc, re.I) and re.search(r"\b(not|no|without|unable|do not)\b.{0,30}sponsor", desc, re.I):
            return "no-sponsorship-ai+text"

    if days_since(it.get("date_posted"), today) > window_days:
        return "out-of-window"

    jid = it.get("id") or hashlib.sha256(f"{org}{t.lower()}{it.get('url') or ''}".encode()).hexdigest()[:16]
    if jid in seen_ids:
        return "already-shown-prior-run"

    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--window-days", type=int, required=True)
    ap.add_argument("--today", default=datetime.date.today().isoformat())
    ap.add_argument("--state", default=os.path.expanduser("~/.job_search/state.json"))
    ap.add_argument("--samples", type=int, default=4, help="Sample items to show per drop bucket")
    args = ap.parse_args()

    today = datetime.date.fromisoformat(args.today)

    with open(args.dataset, "r", encoding="utf-8") as f:
        items = json.load(f)["items"]
    with open(args.state, "r", encoding="utf-8") as f:
        state = json.load(f)
    seen_ids = set(state.get("seen_job_ids", []))
    applied_lower = set(c.lower() for c in state["preferences"].get("applied_or_tracking", []))

    buckets = defaultdict(list)
    kept = 0
    for it in items:
        reason = should_drop(it, applied_lower, seen_ids, args.window_days, today)
        if reason:
            buckets[reason].append(it)
        else:
            kept += 1

    total = len(items)
    print(f"# Drop audit — {total} input items, {kept} kept, {total - kept} dropped\n")
    sorted_buckets = sorted(buckets.items(), key=lambda kv: -len(kv[1]))
    for reason, lst in sorted_buckets:
        print(f"## {reason} — {len(lst)} dropped ({len(lst)/total*100:.0f}%)")
        for it in lst[:args.samples]:
            t = (it.get("title") or "").strip()
            o = (it.get("organization") or "—").strip() or "—"
            u = it.get("url") or ""
            src = it.get("source") or "?"
            lvl = it.get("ai_experience_level") or "?"
            print(f"  · [{src}] {t!r} — {o} (lvl={lvl})")
            print(f"      {u}")
            if reason in ("yoe>=4-required", "no-sponsorship", "citizenship/clearance", "no-sponsorship-ai+text", "defense", "defense-employer"):
                desc = (it.get("description_text") or "")
                m = None
                if reason == "yoe>=4-required":
                    for mm in YOE_RE.finditer(desc[:4000]):
                        yr = int(mm.group(1))
                        if yr >= 4:
                            m = mm; break
                elif reason.startswith("no-sponsorship"):
                    for p in NO_SPONSOR_PATS:
                        mm = re.search(p, desc, re.I)
                        if mm: m = mm; break
                elif reason == "citizenship/clearance":
                    for p in CITIZENSHIP_PATS:
                        mm = re.search(p, desc, re.I)
                        if mm: m = mm; break
                if m:
                    s = max(0, m.start()-60); e = min(len(desc), m.end()+60)
                    snippet = re.sub(r"\s+", " ", desc[s:e]).strip()
                    print(f"      …{snippet}…")
        print()


if __name__ == "__main__":
    main()
