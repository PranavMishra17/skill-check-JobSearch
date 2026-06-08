"""hire_search.py — orchestrate Apify hire-search outputs into jobs_ui/hires.js.

Inputs: two JSON files (`{"items":[...]}`) — one from
  apt_marble/linkedin-hiring-posts-scraper
and one from
  apt_marble/linkedIn-recruiter-scraper
Normalizes, dedupes against `state.seen_hire_ids`, cross-references companies
in `jobs_ui/data.js`, scores, and prepends a new session to
`jobs_ui/hires.js` (the file the static `hires.html` consumes).

Usage:
  python hire_search.py \\
    --hiring-posts <path1> \\
    --recruiters <path2> \\
    --today 2026-06-04 \\
    --label "us-ai"
"""
import json, os, re, hashlib, datetime, sys, io, argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ap = argparse.ArgumentParser()
ap.add_argument("--hiring-posts", required=True)
ap.add_argument("--recruiters", required=True)
ap.add_argument("--today", default=datetime.date.today().isoformat())
ap.add_argument("--label", default="us-ai", help="Slug for the session id, e.g. 'us-ai', 'remote-llm', 'india'")
ap.add_argument("--max-age-days", type=int, default=14,
                help="Drop hiring posts older than this many days (decoded from LinkedIn activity ID).")
ap.add_argument("--state", default=os.path.expanduser("~/.job_search/state.json"))
ap.add_argument("--sessions-dir", default=os.path.expanduser("~/.job_search/sessions"))
ap.add_argument("--html-data", default="E:/_Resume-Curator/job_search/jobs_ui/hires.js")
ap.add_argument("--jobs-data", default="E:/_Resume-Curator/job_search/jobs_ui/data.js",
                help="Path to jobs data.js used for cross-referencing companies.")
ap.add_argument("--backfill", action="store_true")
args = ap.parse_args()

TODAY = datetime.date.fromisoformat(args.today)
SESSION_ID = f"{TODAY.isoformat()}_{args.label}"

# ---------- Load state + jobs companies for cross-ref ----------
with open(args.state, "r", encoding="utf-8") as f:
    state = json.load(f)
state.setdefault("seen_hire_ids", [])
state.setdefault("hire_session_log", [])
seen_hires = set(state.get("seen_hire_ids", []))

# Extract company set from jobs_ui/data.js (the /job-search history)
jobs_companies = set()
if os.path.exists(args.jobs_data):
    try:
        with open(args.jobs_data, "r", encoding="utf-8") as f:
            content = f.read()
        m = re.search(r"window\.JOB_SESSIONS\s*=\s*(.*?);?\s*$", content, flags=re.S)
        if m:
            for sess in json.loads(m.group(1)):
                for j in sess.get("jobs", []):
                    if j.get("company"):
                        jobs_companies.add(j["company"].lower().strip())
    except Exception as e:
        print(f"warning: could not parse jobs data.js ({e})", file=sys.stderr)

# ---------- Helpers ----------
def stable_id(*parts):
    return hashlib.sha256("||".join(p.lower() if p else "" for p in parts).encode()).hexdigest()[:16]

# LinkedIn activity IDs are Snowflake-style: high 41 bits = unix MILLISECONDS when shifted >> 22.
# Verified: ID 7460743380692705280 >> 22 = 1778554406968 ms ≈ 2026-05-18 UTC.
_ACT_RE = re.compile(r"activity[-_:](\d{15,25})")
def post_date_from_url(url):
    if not url: return None
    m = _ACT_RE.search(url)
    if not m: return None
    try:
        act_id = int(m.group(1))
        unix_ms = act_id >> 22
        # Sanity: post must be between 2015 and ~2050 (in ms)
        if unix_ms < 1_420_000_000_000 or unix_ms > 2_500_000_000_000: return None
        return datetime.date.fromtimestamp(unix_ms / 1000)
    except Exception:
        return None

# Frontier-lab / high-signal company keywords
FRONTIER = {"openai", "anthropic", "cohere", "deepmind", "google deepmind", "xai", "mistral", "perplexity",
            "scale ai", "ai fund", "andrew ng", "harvey", "sierra", "character.ai", "inflection", "adept"}
YC_TECHSTARS = {"yc", "y combinator", "techstars"}

def derive_company_from_post(item):
    """Try to extract a company name from a hiring post's fields."""
    raw = item.get("hiringCompany") or ""
    if raw and len(raw) > 1 and not re.search(r"^(Senior|the Sr|Engineering|Data Science|Software)\b", raw):
        return raw.strip()
    snippet = item.get("postSnippet") or ""
    # Try to grab "@ <Company>" or "at <Company>"
    m = re.search(r"\b(?:at|@)\s+([A-Z][A-Za-z0-9 .&\-]{1,40}?)(?:[,.\|]|$)", snippet)
    if m: return m.group(1).strip()
    return None

def parse_location(s):
    if not s: return None
    s = s.replace("Read more", "").strip()
    # Try "City, State, United States" pattern
    m = re.search(r"([A-Z][A-Za-z .\-]+?,\s*[A-Z][A-Za-z .\-]+?,\s*United States)", s)
    if m: return m.group(1)
    m = re.search(r"([A-Z][A-Za-z .\-]+?,\s*United States)", s)
    if m: return m.group(1)
    return None

# ---------- Scoring ----------
SCOPE_ROLES = {"ai engineer", "llm engineer", "ml engineer", "machine learning engineer",
               "founding engineer", "forward deployed", "applied ai", "applied scientist",
               "agentic", "research engineer", "software engineer ai"}

def score_hire(item):
    """Score a normalized hire 0-100."""
    pts = 0
    title = (item.get("title") or "").lower()
    company = (item.get("company") or "").lower()
    role = (item.get("hiring_for") or "").lower()
    context = (item.get("context") or "").lower()
    bag = f"{title} {company} {role} {context}"

    # Company signal (max 30)
    if any(f in company for f in FRONTIER): pts += 30
    elif company and company in jobs_companies: pts += 25  # already matched in /job-search
    elif any(k in bag for k in YC_TECHSTARS): pts += 22
    elif "ai" in company or "ml" in company: pts += 18  # AI-named company
    elif company: pts += 10
    else: pts += 5

    # Role / niche alignment (max 25)
    role_match = sum(1 for r in SCOPE_ROLES if r in bag)
    if role_match >= 2: pts += 25
    elif role_match == 1: pts += 18
    elif "ai" in role or "ml" in role: pts += 12
    else: pts += 5

    # Title quality (max 20)
    if re.search(r"\b(ai|ml|machine learning|technical|engineering|founding|head of talent)\b", title):
        if "ai" in title or "ml" in title or "machine learning" in title: pts += 20
        elif "founding" in title: pts += 18
        elif "technical" in title or "engineering" in title: pts += 15
        elif "head of talent" in title: pts += 14
        else: pts += 10
    else:
        pts += 5

    # Intent / source (max 15)
    if item.get("intent") == "Medium": pts += 12
    elif item.get("intent") == "High": pts += 15
    elif item.get("intent") == "Low": pts += 5
    elif item.get("kind") == "recruiter": pts += 10  # standing presence is reasonable signal

    # Location (max 10): US-only filter is already applied in actor; small constant
    if "united states" in (item.get("location") or "").lower() or item.get("location") is None:
        pts += 10

    return max(0, min(100, pts))

# ---------- Normalize ----------
def norm_post(it):
    company = derive_company_from_post(it)
    post_url = it.get("postUrl") or ""
    pd = post_date_from_url(post_url)
    age_days = (TODAY - pd).days if pd else None
    return {
        "kind": "post",
        "name": (it.get("recruiterName") or "").replace("'s Post", "").strip() or None,
        "title": "Posted: " + (it.get("hiringRole") or "Hiring Role"),
        "company": company,
        "linkedin_url": post_url,
        "post_url": post_url,
        "location": "United States",
        "hiring_for": it.get("hiringRole"),
        "context": (it.get("postSnippet") or "").strip(),
        "intent": it.get("hiringIntent"),
        "matched_keyword": it.get("hiringKeywordMatched"),
        "post_date": pd.isoformat() if pd else None,
        "post_age_days": age_days,
        "_at": it.get("timestamp"),
    }

def norm_recruiter(it):
    return {
        "kind": "recruiter",
        "name": it.get("fullName") or f"{it.get('firstName','')} {it.get('lastName','')}".strip(),
        "title": it.get("currentTitle") or "",
        "company": it.get("company"),
        "linkedin_url": it.get("linkedinUrl") or "",
        "post_url": None,
        "location": parse_location(it.get("snippet") or "") or "United States",
        "hiring_for": None,
        "context": (it.get("snippet") or "").replace("Read more", "").strip(),
        "intent": None,
        "niche": it.get("hiringNiche"),
        "_at": it.get("timestamp"),
    }

# ---------- Load + process ----------
with open(args.hiring_posts, "r", encoding="utf-8") as f:
    posts = json.load(f)["items"]
with open(args.recruiters, "r", encoding="utf-8") as f:
    recruiters = json.load(f)["items"]

normalized = []
for it in posts:
    n = norm_post(it)
    n["_id"] = stable_id(n["kind"], n["linkedin_url"])
    normalized.append(n)
for it in recruiters:
    n = norm_recruiter(it)
    n["_id"] = stable_id(n["kind"], n["linkedin_url"])
    normalized.append(n)

# Dedup against seen, and within-run by _id
dropped = {"already-seen": 0, "duplicate-in-run": 0, "filtered-niche": 0,
           "post-too-old": 0, "post-no-date": 0}
ids_in_run = set()
keep = []
for n in normalized:
    if n["_id"] in seen_hires and not args.backfill:
        dropped["already-seen"] += 1
        continue
    if n["_id"] in ids_in_run:
        dropped["duplicate-in-run"] += 1
        continue
    if (n.get("niche") or "").lower() == "frontend developers":
        dropped["filtered-niche"] += 1
        continue
    # Hiring-post age filter (recruiters have no date — they're standing presence, keep them)
    if n["kind"] == "post":
        age = n.get("post_age_days")
        if age is None:
            # Unparseable date — keep but flag (don't drop, the actor returns recent posts mostly)
            dropped["post-no-date"] += 1
        elif age > args.max_age_days:
            dropped["post-too-old"] += 1
            continue
    ids_in_run.add(n["_id"])
    n["score"] = score_hire(n)
    n["company_in_jobs"] = bool(n.get("company") and n["company"].lower().strip() in jobs_companies)
    keep.append(n)

keep.sort(key=lambda x: -x["score"])
for i, n in enumerate(keep, 1):
    n["rank"] = i

# ---------- Write hires.js ----------
def update_html_data(path, new_session):
    sessions = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            m = re.search(r"window\.HIRE_SESSIONS\s*=\s*(.*?);?\s*$", content, flags=re.S)
            if m and m.group(1).strip(): sessions = json.loads(m.group(1))
        except Exception as e:
            print(f"warning: could not parse existing hires.js ({e})", file=sys.stderr)
            sessions = []
    sessions = [s for s in sessions if s.get("id") != new_session["id"]]
    sessions.insert(0, new_session)
    tmp = path + ".tmp"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("window.HIRE_SESSIONS = ")
        json.dump(sessions, f, ensure_ascii=False, indent=2)
        f.write(";\n")
    os.replace(tmp, path)

new_session = {
    "id": SESSION_ID,
    "date": TODAY.isoformat(),
    "label": args.label,
    "raw_total": len(normalized),
    "after_dedup": len(keep),
    "drop_log": dropped,
    "people": keep,
}
update_html_data(args.html_data, new_session)

# ---------- Write MD backup ----------
os.makedirs(args.sessions_dir, exist_ok=True)
md_path = os.path.join(args.sessions_dir, f"hires_{TODAY.isoformat()}_{args.label}.md")
lines = [f"# Hire Search — {args.label} — {TODAY.isoformat()}", ""]
lines.append(f"**{len(keep)} people surfaced** (from {len(normalized)} raw).")
lines.append("")
for n in keep:
    name = n["name"] or "(unknown poster)"
    title = n["title"]
    co = n.get("company") or "—"
    url = n["linkedin_url"]
    kind = n["kind"]
    flag = " [match w/ job session]" if n["company_in_jobs"] else ""
    lines.append(f"### #{n['rank']} · {n['score']}/100 · {kind}")
    lines.append(f"**[{name}]({url})** — *{title}* — **{co}**{flag}")
    if n["kind"] == "post" and n.get("hiring_for"):
        lines.append(f"  Hiring for: **{n['hiring_for']}**  ·  Intent: {n.get('intent') or '?'}")
    snippet = (n.get("context") or "").replace("\n", " ")[:240]
    if snippet: lines.append(f"  > {snippet}")
    lines.append("")
with open(md_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

# ---------- State update ----------
if not args.backfill:
    state["seen_hire_ids"] = sorted(set(state.get("seen_hire_ids", [])) | ids_in_run)
    entry = {"date": TODAY.isoformat(), "label": args.label,
             "sources": ["apify:apt_marble/linkedin-hiring-posts-scraper",
                         "apify:apt_marble/linkedIn-recruiter-scraper"],
             "raw": len(normalized), "after_dedup": len(keep), "drop_log": dropped,
             "output_html_data": args.html_data, "output_md": md_path}
    last = state["hire_session_log"][-1] if state["hire_session_log"] else None
    if last and last.get("date") == TODAY.isoformat() and last.get("label") == args.label:
        state["hire_session_log"][-1] = entry
    else:
        state["hire_session_log"].append(entry)
    tmp = args.state + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    os.replace(tmp, args.state)

# ---------- Stdout summary ----------
print(f"# Hire Search — {args.label}  ({TODAY.isoformat()})\n")
print(f"**{len(keep)} people surfaced** (from {len(normalized)} raw).")
print(f"  Posts: {sum(1 for x in keep if x['kind']=='post')}  ·  Recruiters: {sum(1 for x in keep if x['kind']=='recruiter')}")
print(f"\n  HTML: `E:\\_Resume-Curator\\job_search\\jobs_ui\\hires.html`")
print(f"  MD:   `{md_path}`\n")
print(f"## Top 8 preview\n")
for n in keep[:8]:
    name = n["name"] or "(unknown)"
    print(f"- **{n['score']}/100** · [{name}]({n['linkedin_url']}) — *{n['title']}* — {n.get('company') or '—'}")
print(f"\nDrop log: " + ", ".join(f"`{k}`={v}" for k, v in dropped.items()))
