"""Re-render scored results from a cached Apify dataset into a clean MD file.

Filter posture (locked-in per user feedback 2026-06-02):
- DROP any role with seniority >= 5 yrs (ai_experience_level in {"5-10","10+"})
- DROP any title containing Senior/Sr/Lead/Staff/Principal/Manager/Director/VP/Head
- DROP any role that explicitly excludes visa sponsorship (any "must be authorized
  to work in the U.S. without sponsorship" / "no sponsorship" / "ineligible for
  sponsorship" phrasing). These are NOT down-ranked — they are removed.
- DROP citizenship / clearance / defense roles, recruitment agencies, non-US,
  current employer (alfred_), and any company in applied_or_tracking.
- DROP duplicate postings (same company + normalised title).
- DROP roles outside the time window.

Output:
- All survivors written to an MD file at ~/.job_search/sessions/jobs_<date>_<windowd>.md
- Short text summary printed to stdout for inline display.

Layout (per role):
    ### #N · Match X/100
    **[Title](apply_url)** — **Company**
    <meta line>: location · salary · posted · experience · sponsorship
    Short responsibility one-liner.
"""
import json, os, re, hashlib, datetime, sys, io, argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ap = argparse.ArgumentParser()
ap.add_argument("--dataset", required=True)
ap.add_argument("--window-days", type=int, default=10)
ap.add_argument("--today", default="2026-06-02")
ap.add_argument("--state", default=os.path.expanduser("~/.job_search/state.json"))
ap.add_argument("--sessions-dir", default=os.path.expanduser("~/.job_search/sessions"))
ap.add_argument("--html-data", default="E:/_Resume-Curator/job_search/jobs_ui/data.js",
                help="Path to data.js consumed by jobs_ui/index.html. The render appends a session here.")
ap.add_argument("--backfill", action="store_true",
                help="Backfill mode: do NOT dedup against seen_job_ids and do NOT update state.json. "
                     "Use for rebuilding past sessions from cached datasets.")
args = ap.parse_args()

TODAY = datetime.date.fromisoformat(args.today)
WINDOW_DAYS = args.window_days

# --- Scoring config
CANDIDATE_SKILLS = {
    "python","typescript","javascript","c++","c#","java","rust",
    "pytorch","tensorflow","langchain","libtorch","google adk","agent development kit",
    "livekit","coqui tts","xtts-v2","huggingface","hugging face",
    "fastapi","flask","node.js","express","hono","asp.net core","next.js",
    "react","tailwind",
    "postgresql","postgres","mongodb","redis","supabase","pinecone","cosmos db",
    "vector database","vector search",
    "aws","sagemaker","mlflow","azure","docker","ci/cd","vercel","railway","render","kubernetes",
    "deepgram","openai tts","cartesia","silero","webrtc","int8 quantization",
    "multi-agent","agentic","mcp","model context protocol","rag",
    "retrieval-augmented generation","voice ai","llm","evaluation","production llm","c++ inference","raii",
    "transformer","attention","embeddings","fine-tuning","rlhf",
    "openai","anthropic","gemini","claude","gpt","llama","mistral",
    "tool calling","tool-calling","function calling",
}
DOMAIN_STRONG = {"multi-agent","agentic","rag","retrieval-augmented","voice ai","llm","mlops",
                 "production llm","eval harness","evaluation","tool-calling","tool calling","mcp",
                 "agent orchestration","foundation model","fine-tuning","llmops"}
DOMAIN_PARTIAL = {"machine learning","ml platform","data pipeline","data engineering","classical ml","computer vision","nlp"}
FRONTIER_LABS = {"openai","anthropic","cohere","deepmind","google deepmind","xai","mistral","inflection",
                 "perplexity","adept","character.ai","scale ai","scale","harvey","sierra"}
YC_TECHSTARS_HINT = {"yc","y combinator","y-combinator","techstars"}

CITIZENSHIP_PATS = [r"\bus citizenship\b",r"\bu\.s\. citizenship\b",r"must be a us citizen",r"must be a u\.s\. citizen",
                    r"\bts/sci\b",r"\btop secret\b",r"\bsecret clearance\b",r"active clearance",r"security clearance",
                    r"us citizens? or green card holders? only",r"green card holders? only",r"only.{0,30}u\.s\. citizens"]

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
WILL_SPONSOR_PATS = [r"we sponsor",r"sponsorship available",r"h-?1b sponsorship",r"we will sponsor",r"we offer sponsorship",
                     r"visa sponsorship (?:is )?(?:available|offered|provided)"]

# Title-based DROP patterns (case-insensitive, word-boundary aware)
TITLE_SENIOR_DROP = re.compile(
    r"\b(senior|sr\.?|lead|staff|principal|manager|director|head\s+of|vp|sr\s+staff|chief)\b", re.I)
PURE_FRONTEND = re.compile(r"\bfront.?end (developer|engineer)\b|\bui developer\b|\breact developer\b", re.I)

# Years-of-experience drop heuristic: "X+ years" with X >= 4
YOE_RE = re.compile(r"\b(\d{1,2})\+?\s*(?:to|–|-)?\s*\d{0,2}\s*(?:\+)?\s*years?\b(?!\s+experience\s+is\s+preferred)", re.I)

COMPANY_EXCLUDE = {"alfred_","alfred"}
TITLE_SCOPE = [
    # core engineering
    "ai engineer","ml engineer","machine learning engineer","llm engineer",
    "founding engineer","forward deployed","forward-deployed",
    "applied ai","applied scientist","applied ml",
    "research engineer","research scientist",
    "ai/ml","ai engineering","software engineer","software developer",
    "ai infrastructure","ml infrastructure","platform engineer",
    "ai researcher","ml researcher","deep learning engineer",
    "ai platform","ml platform","ai systems","data scientist","ai associate",
    "computer scientist","generative ai",
    # 2026 agentic / LLM-tooling wave
    "agentic","ai agent","agent engineer","agentic engineer","agentic ai",
    "vibe coder","vibe coding","vibe engineer",
    "claude developer","claude engineer","gpt developer","gpt engineer",
    "llm developer","llm tooling","llm ops","llmops","mlops",
    "prompt engineer","prompt architect",
    "ai builder","ai developer","ai automation","ai integration",
    "ai solutions engineer","ai solutions architect","ai tooling",
    "ai product engineer","ai workflow",
    "langchain","langgraph","copilot engineer","cursor engineer",
    "rag engineer","retrieval engineer",
    "ai research",  # keep for "AI Research Engineer" industry titles (excludes academic fellowships)
]
# Academic-research roles intentionally NOT in scope:
# "research fellow", "postdoctoral", "postdoc", "fellowship"  — user is targeting industry

def any_re(text, pats): return text and any(re.search(p, text, re.I) for p in pats)
def days_since(ds):
    if not ds: return 999
    try: return (TODAY - datetime.datetime.fromisoformat(ds.replace("Z","+00:00")).date()).days
    except: return 999
def stable_id(c,t,u): return hashlib.sha256(f"{(c or '').lower()}{(t or '').lower()}{u or ''}".encode()).hexdigest()[:16]
def norm_title(t): return re.sub(r"[^a-z0-9 ]", " ", (t or "").lower()).split()

def has_high_yoe_requirement(desc):
    """Drop if JD demands 4+ years anywhere a required-experience phrase appears."""
    if not desc: return False
    for m in YOE_RE.finditer(desc[:4000]):
        try:
            years = int(m.group(1))
        except: continue
        if years >= 4:
            # only count if appears near "experience", "required", "minimum"
            window = desc[max(0, m.start()-80):m.end()+80].lower()
            if re.search(r"(experience|required|minimum|at least|must have|preferred)", window):
                return True
    return False

def skill_match(it):
    skills = set(s.lower() for s in (it.get("ai_key_skills") or []))
    desc = (it.get("description_text") or "").lower()
    score, matched = 0, set()
    for cs in CANDIDATE_SKILLS:
        if cs in skills: score += 3; matched.add(cs)
        elif cs in desc: score += 1; matched.add(cs)
    return min(score, 30), sorted(matched)

def domain_score(it):
    bag = " ".join([it.get("title") or "", it.get("ai_core_responsibilities") or "",
                    " ".join(it.get("ai_key_skills") or []), it.get("description_text") or ""]).lower()
    s = sum(1 for k in DOMAIN_STRONG if k in bag)
    p = sum(1 for k in DOMAIN_PARTIAL if k in bag)
    if s >= 3: return 25
    if s == 2: return 22
    if s == 1: return 18
    if p >= 2: return 14
    if p == 1: return 9
    return 4

def seniority_pts(it):
    lvl, title = it.get("ai_experience_level"), (it.get("title") or "").lower()
    if "founding" in title or "forward deployed" in title or "forward-deployed" in title: return 15
    if lvl == "0-2": return 15
    if lvl == "2-5": return 13
    return 8  # surviving rows shouldn't have 5-10/10+ anymore

def company_pts(it):
    org = (it.get("organization") or "").lower()
    bag = f"{(it.get('linkedin_org_description') or '').lower()} {' '.join(it.get('linkedin_org_specialties') or []).lower()} {(it.get('linkedin_org_industry') or '').lower()}"
    if any(lab in org for lab in FRONTIER_LABS): return 15
    if any(h in bag for h in YC_TECHSTARS_HINT): return 12
    if "artificial intelligence" in bag or "machine learning" in bag or "research services" in bag: return 10
    if "software" in bag or "saas" in bag: return 8
    if "consulting" in bag or "staffing" in bag: return 3
    return 5

def location_pts(it):
    arr = it.get("ai_work_arrangement") or ""
    locs = " ".join(it.get("locations_derived") or []).lower()
    if arr in ("Remote OK","Remote Solely"): return 10
    if "new york" in locs or "manhattan" in locs or "brooklyn" in locs: return 9
    if "san francisco" in locs or "palo alto" in locs or "mountain view" in locs: return 8
    if arr == "Hybrid": return 7
    if arr == "On-site": return 5
    return 5

def recency_pts(it):
    d = days_since(it.get("date_posted"))
    return 5 if d <= 1 else 3 if d <= 3 else 1 if d <= 7 else 0

def sponsorship(it):
    """Returns (score_adj, label). Sponsorship-excluded roles are dropped earlier;
    here we only mark available / unknown."""
    desc = it.get("description_text") or ""
    if it.get("ai_visa_sponsorship") is True: return 5, "available"
    if any_re(desc, WILL_SPONSOR_PATS): return 5, "available"
    return 0, "unknown"

def should_drop(it, applied_lower):
    t = it.get("title") or ""
    org = (it.get("organization") or "").lower()
    desc = it.get("description_text") or ""

    # Geographic / employer rules
    countries = it.get("countries_derived") or []
    if not countries or not all("United States" in c for c in countries): return "non-US"
    if it.get("linkedin_org_recruitment_agency_derived") is True: return "agency"
    if org in COMPANY_EXCLUDE: return "current-employer"
    if org in applied_lower: return "already-applied"

    # Title scope
    if not any(k in t.lower() for k in TITLE_SCOPE): return "title-out-of-scope"
    if TITLE_SENIOR_DROP.search(t): return "title-too-senior"
    if PURE_FRONTEND.search(t): return "pure-frontend"

    # Experience level
    lvl = it.get("ai_experience_level")
    if lvl in ("5-10", "10+"): return f"ai-experience-level:{lvl}"
    if has_high_yoe_requirement(desc): return "yoe>=4-required"

    # Citizenship / clearance / defense
    if any_re(desc, CITIZENSHIP_PATS): return "citizenship/clearance"
    tax = " ".join(it.get("ai_taxonomies_a") or []).lower()
    if "defense" in tax or "military" in tax: return "defense"
    if re.search(r"\b(department of (?:war|defense)|\bdod\b|military|national security)\b", desc, re.I):
        if any(w in (it.get("linkedin_org_description") or "").lower() for w in ["defense","military","intelligence","national security"]):
            return "defense-employer"

    # Sponsorship hard filter (NEW): explicit no-sponsor language drops the role
    if any_re(desc, NO_SPONSOR_PATS): return "no-sponsorship"
    # Also drop if AI field marks sponsorship false AND there's matching language
    if it.get("ai_visa_sponsorship") is False:
        # AI is often wrong; only drop when JD also contains an exclusionary phrase
        # (handled above) OR when org policy phrase fragments exist
        if re.search(r"sponsor(?:ship)?", desc, re.I) and re.search(r"\b(not|no|without|unable|do not)\b.{0,30}sponsor", desc, re.I):
            return "no-sponsorship-ai+text"

    return None

# --- Load
with open(args.dataset, "r", encoding="utf-8") as f:
    items = json.load(f)["items"]
with open(args.state, "r", encoding="utf-8") as f:
    state = json.load(f)
seen = set(state.get("seen_job_ids", []))
applied_lower = set(c.lower() for c in state["preferences"].get("applied_or_tracking", []))

scored, drop_counts = [], {}
seen_keys = set()  # (org, normalised-title) to collapse multi-board duplicates
for it in items:
    reason = should_drop(it, applied_lower)
    if reason:
        drop_counts[reason] = drop_counts.get(reason, 0) + 1
        continue
    if days_since(it.get("date_posted")) > WINDOW_DAYS:
        drop_counts["out-of-window"] = drop_counts.get("out-of-window", 0) + 1
        continue

    dupe_key = ((it.get("organization") or "").lower(), tuple(norm_title(it.get("title"))))
    if dupe_key in seen_keys:
        drop_counts["duplicate-in-run"] = drop_counts.get("duplicate-in-run", 0) + 1
        continue
    seen_keys.add(dupe_key)

    jid = stable_id(it.get("organization"), it.get("title"), it.get("url"))
    if jid in seen and not args.backfill:
        drop_counts["already-shown-prior-run"] = drop_counts.get("already-shown-prior-run", 0) + 1
        continue
    it["_job_id"] = jid
    s_sk, matched = skill_match(it)
    s_d, s_s, s_c, s_l, s_r = domain_score(it), seniority_pts(it), company_pts(it), location_pts(it), recency_pts(it)
    s_sp, sp_label = sponsorship(it)
    total = max(0, min(100, s_sk + s_d + s_s + s_c + s_l + s_r + s_sp))
    scored.append({"it": it, "matched": matched, "label": sp_label,
                   "parts": {"skill": s_sk, "domain": s_d, "sen": s_s, "co": s_c, "loc": s_l, "rec": s_r, "spon": s_sp},
                   "total": total})

scored.sort(key=lambda x: -x["total"])

# --- Helpers for output
def fmt_salary(it):
    smin, smax = it.get("ai_salary_minvalue"), it.get("ai_salary_maxvalue")
    if smin and smax and smax > 1000: return f"${smin/1000:.0f}–${smax/1000:.0f}k"
    if smin and smin > 1000: return f"${smin/1000:.0f}k+"
    return None

US_STATE = {
    "Alabama":"AL","Alaska":"AK","Arizona":"AZ","Arkansas":"AR","California":"CA","Colorado":"CO","Connecticut":"CT",
    "Delaware":"DE","Florida":"FL","Georgia":"GA","Hawaii":"HI","Idaho":"ID","Illinois":"IL","Indiana":"IN","Iowa":"IA",
    "Kansas":"KS","Kentucky":"KY","Louisiana":"LA","Maine":"ME","Maryland":"MD","Massachusetts":"MA","Michigan":"MI",
    "Minnesota":"MN","Mississippi":"MS","Missouri":"MO","Montana":"MT","Nebraska":"NE","Nevada":"NV","New Hampshire":"NH",
    "New Jersey":"NJ","New Mexico":"NM","New York":"NY","North Carolina":"NC","North Dakota":"ND","Ohio":"OH",
    "Oklahoma":"OK","Oregon":"OR","Pennsylvania":"PA","Rhode Island":"RI","South Carolina":"SC","South Dakota":"SD",
    "Tennessee":"TN","Texas":"TX","Utah":"UT","Vermont":"VT","Virginia":"VA","Washington":"WA","West Virginia":"WV",
    "Wisconsin":"WI","Wyoming":"WY","District of Columbia":"DC"
}
def fmt_loc(it):
    locs = it.get("locations_derived") or []
    if not locs: return "—"
    out = []
    for l in locs[:2]:
        parts = [p.strip() for p in l.split(",")]
        city = parts[0] if parts else ""
        region = parts[1] if len(parts) >= 2 else ""
        ab = US_STATE.get(region, region[:2].upper() if region else "")
        out.append(f"{city}, {ab}" if ab else city)
    if len(locs) > 2: out.append(f"+{len(locs)-2}")
    return " / ".join(out)

def fmt_arrangement(it):
    arr = it.get("ai_work_arrangement") or ""
    return {"Remote OK":"Remote","Remote Solely":"Remote","Hybrid":"Hybrid","On-site":"On-site"}.get(arr, arr or "—")

def fmt_posted(it):
    d = days_since(it.get("date_posted"))
    if d == 0: return "today"
    if d == 1: return "1 day ago"
    return f"{d} days ago"

def fmt_sponsor(label):
    return {"available":"sponsors visa","unknown":"sponsorship not stated"}.get(label, label)

# --- Write MD file
window_label = f"{WINDOW_DAYS}d"
os.makedirs(args.sessions_dir, exist_ok=True)
md_path = os.path.join(args.sessions_dir, f"jobs_{TODAY.isoformat()}_{window_label}.md")

lines = []
lines.append(f"# Job Search — {window_label} window — {TODAY.isoformat()}")
lines.append("")
lines.append(f"**{len(scored)} survivors** out of 100 crawled. Source: Apify `fantastic-jobs/career-site-job-listing-api`.")
lines.append("")
lines.append("**Filters applied:** US-only · FT W-2 · entry / junior / mid (0–2 or 2–5 yrs only) · "
             "drops Sr/Senior/Lead/Staff/Principal/Manager/Director/VP/Head titles · "
             "drops roles requiring 4+ years experience · "
             "drops roles that explicitly exclude visa sponsorship · "
             "no defense/military · no clearance/citizenship-gated.")
lines.append("")
lines.append("---")
lines.append("")

for i, s in enumerate(scored, 1):
    it = s["it"]
    title = (it.get("title") or "").strip()
    org = (it.get("organization") or "").strip()
    url = it.get("url") or ""

    meta_bits = [
        fmt_loc(it),
        fmt_arrangement(it),
        fmt_salary(it),
        fmt_posted(it),
        (it.get("ai_experience_level") or "") + " yrs" if it.get("ai_experience_level") else None,
        fmt_sponsor(s["label"]),
    ]
    meta_line = " · ".join([m for m in meta_bits if m])

    resp = (it.get("ai_core_responsibilities") or "").strip()
    resp = re.sub(r"\s+", " ", resp)[:280]
    if resp and not resp.endswith("."): resp += ("…" if len(resp) == 280 else ".")

    lines.append(f"### #{i} · Match {s['total']}/100")
    lines.append(f"**[{title}]({url})** — **{org}**")
    lines.append("")
    lines.append(meta_line)
    lines.append("")
    if resp:
        lines.append(resp)
        lines.append("")
    lines.append("---")
    lines.append("")

# Drop reasons appendix (helps debug)
lines.append("## Drop log")
lines.append("")
for k, v in sorted(drop_counts.items(), key=lambda x: -x[1]):
    lines.append(f"- `{k}` — {v}")
lines.append("")

with open(md_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

# --- Build HTML-friendly session record + write to data.js
def html_session():
    return {
        "id": f"{TODAY.isoformat()}_{window_label}",
        "date": TODAY.isoformat(),
        "window": window_label,
        "crawled": len(items),
        "survived": len(scored),
        "drop_log": drop_counts,
        "source": "apify:fantastic-jobs/career-site-job-listing-api",
        "jobs": [
            {
                "rank": i,
                "score": s["total"],
                "title": (s["it"].get("title") or "").strip(),
                "company": (s["it"].get("organization") or "").strip(),
                "url": s["it"].get("url") or "",
                "location": fmt_loc(s["it"]),
                "arrangement": fmt_arrangement(s["it"]),
                "salary": fmt_salary(s["it"]) or "",
                "posted": fmt_posted(s["it"]),
                "experience": s["it"].get("ai_experience_level") or "",
                "sponsorship": s["label"],
                "description": re.sub(r"\s+", " ", (s["it"].get("ai_core_responsibilities") or "").strip())[:280],
            } for i, s in enumerate(scored, 1)
        ],
    }

def update_data_js(path, new_session):
    sessions = []
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            m = re.search(r"window\.JOB_SESSIONS\s*=\s*(.*?);?\s*$", content, flags=re.S)
            if m: sessions = json.loads(m.group(1))
        except Exception as e:
            print(f"warning: could not parse existing data.js ({e}); starting fresh", file=sys.stderr)
            sessions = []
    # Replace any prior session with the same id
    sessions = [s for s in sessions if s.get("id") != new_session["id"]]
    # Newest first
    sessions.insert(0, new_session)
    # Atomic write
    tmp = path + ".tmp"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("window.JOB_SESSIONS = ")
        json.dump(sessions, f, ensure_ascii=False, indent=2)
        f.write(";\n")
    os.replace(tmp, path)

new_session = html_session()
update_data_js(args.html_data, new_session)

# --- Update state.json (skipped in backfill mode)
if not args.backfill:
    shown_ids = [s["it"]["_job_id"] for s in scored]
    state["seen_job_ids"] = sorted(set(state.get("seen_job_ids", [])) | set(shown_ids))
    last = state["session_log"][-1] if state["session_log"] else None
    session_entry = {
        "date": TODAY.isoformat(),
        "window": window_label,
        "sources": ["apify:fantastic-jobs/career-site-job-listing-api"],
        "raw_crawled": len(items),
        "after_filter": len(scored),
        "drop_log": drop_counts,
        "output_md": md_path,
        "output_html_data": args.html_data,
        "notes": "Tightened filters (no senior/lead/staff, no no-sponsorship JDs, no 4+ YoE). HTML UI: jobs_ui/index.html."
    }
    if last and last.get("date") == TODAY.isoformat() and last.get("window") == window_label:
        state["session_log"][-1] = session_entry
    else:
        state["session_log"].append(session_entry)
    tmp = args.state + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    os.replace(tmp, args.state)

# --- Stdout summary (compact)
print(f"# Job Search — {window_label} window\n")
print(f"**{len(scored)} survivors** (tightened filters applied). Open in browser:")
html_path = os.path.normpath(os.path.join(os.path.dirname(args.html_data), "index.html"))
print(f"\n  HTML: `{html_path}`")
print(f"  MD:   `{md_path}`\n")
top5 = scored[:5]
print(f"## Top {len(top5)} preview\n")
for i, s in enumerate(top5, 1):
    it = s["it"]
    print(f"{i}. **[{it.get('title')}]({it.get('url')})** — {it.get('organization')}  ·  **{s['total']}/100**")
    meta = " · ".join([m for m in [fmt_loc(it), fmt_arrangement(it), fmt_salary(it), fmt_posted(it)] if m])
    print(f"   {meta}\n")

print(f"\n**Drop log:** " + ", ".join(f"`{k}`={v}" for k, v in sorted(drop_counts.items(), key=lambda x: -x[1])))
print(f"\nOpen the full MD: `{md_path}`")
