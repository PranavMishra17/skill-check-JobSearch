"""hire_crawl.py — profile-flexible, zero-Apify hire-search.

Reuses the LATEST /job-search crawl: walks the top-scoring jobs and, for each,
hunts down the humans who hire for it — using ONLY the job's metadata
(company, title, team, location), never visiting the job URL. Priority order
per job:

    1. recruiter / talent acquisition
    2. head of people / HR leadership
    3. hiring manager / eng-lead
    4. founder / CEO / CTO   (startups)
    5. engineers on/near that team   (LAST RESORT — GitHub commit authors)

For every person found it tries to recover a REAL EMAIL:
    - GitHub commit-author email (exact, when the person is an engineer), else
    - name+domain permutation, graded by a single-connection SMTP RCPT-TO probe
      (verified | mx-ok-guess | catch-all | invalid).

Search backend is pluggable:  brave (API key, primary) | searxng (keyless URL)
Static search-engine scraping is intentionally NOT used — it is anti-bot-blocked
in 2026 (verified: Google/Bing/DDG serve challenge/JS-gated pages even to a real
headless browser, and LinkedIn /in profiles are largely de-indexed).

Target: a list of `--target` (default 50) jobs that each yielded >=1 contact.
If the top-N jobs don't reach the target, it BACKFILLS down the ranked list.

Output: prepends a session to jobs_ui/hires.js (same schema the dashboard reads),
writes an MD backup, updates ~/.job_search/state.json (seen_hire_ids + log).

Usage:
  BRAVE_API_KEY=xxxx python hire_crawl.py --today 2026-07-16 --label us-ai \
      --target 50 --provider brave
  python hire_crawl.py --provider searxng --target 20        # keyless fallback
"""
import argparse, datetime, hashlib, io, json, os, re, sys, time
from pathlib import Path

# Windows console defaults to cp1252; force UTF-8 so ✓/✅/… don't crash prints.
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hire_probe import (name_parts, permutations_for, mx_hosts, github_org_emails)  # reuse proven code
import smtplib

try:
    import requests
except ImportError:
    requests = None


# ─────────────────────────── search providers ───────────────────────────

AGGREGATOR_HOSTS = ("rocketreach.co", "signalhire.com", "theorg.com", "zoominfo.com",
                    "contactout.com", "apollo.io", "lusha.com", "leadiq.com", "kaspr.io")


class SearchError(Exception):
    pass


def brave_search(query, key, count=15, country="us"):
    if requests is None:
        raise SearchError("requests not installed")
    r = requests.get(
        "https://api.search.brave.com/res/v1/web/search",
        headers={"X-Subscription-Token": key, "Accept": "application/json"},
        params={"q": query, "count": count, "country": country, "search_lang": "en",
                "result_filter": "web", "safesearch": "off"},
        timeout=20,
    )
    if r.status_code == 429:
        raise SearchError("brave rate-limited (429) — free tier is 1 query/sec")
    if r.status_code != 200:
        raise SearchError(f"brave HTTP {r.status_code}: {r.text[:120]}")
    data = r.json()
    out = []
    for w in (data.get("web", {}) or {}).get("results", []):
        out.append({"title": w.get("title", ""), "url": w.get("url", ""),
                    "snippet": w.get("description", "")})
    return out


SEARXNG_INSTANCES = ["https://searx.be", "https://baresearch.org", "https://priv.au",
                     "https://search.inetol.net", "https://searx.tiekoetter.com"]


def searxng_search(query, count=15):
    if requests is None:
        raise SearchError("requests not installed")
    ua = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/120 Safari/537.36"}
    last = ""
    for inst in SEARXNG_INSTANCES:
        try:
            r = requests.get(f"{inst}/search", params={"q": query, "format": "json"},
                             headers=ua, timeout=15)
            if r.status_code != 200:
                last = f"{inst} HTTP {r.status_code}"; continue
            res = r.json().get("results", [])
            if res:
                return [{"title": x.get("title", ""), "url": x.get("url", ""),
                         "snippet": x.get("content", "")} for x in res[:count]]
        except Exception as e:
            last = f"{inst}: {type(e).__name__}"
            continue
    raise SearchError(f"no searxng instance returned results ({last})")


def run_search(query, provider, brave_key):
    if provider == "brave":
        if not brave_key:
            raise SearchError("provider=brave but no BRAVE_API_KEY set")
        return brave_search(query, brave_key)
    return searxng_search(query)


# ─────────────────────────── person extraction ───────────────────────────

TITLE_KEYWORDS = {
    "recruiter":       ["recruiter", "talent acquisition", "talent partner", "sourcer", "recruiting"],
    "people":          ["head of people", "head of talent", "people operations", "chief people",
                        "hr manager", "human resources", "head of hr", "people & culture"],
    "hiring-manager":  ["hiring manager", "engineering manager", "director of engineering",
                        "vp engineering", "head of engineering", "eng manager"],
    "founder":         ["founder", "co-founder", "cofounder", "ceo", "cto", "chief executive",
                        "chief technology"],
    "engineer":        ["engineer", "developer", "scientist", "mle", "ml engineer"],
}
_ALL_TITLE_KW = [(k, kw) for k, kws in TITLE_KEYWORDS.items() for kw in kws]

_NAME_RE = re.compile(r"^[A-Z][a-zA-Z.'\-]+(?:\s+[A-Z][a-zA-Z.'\-]+){1,3}$")
# tokens that mean the "name" is actually a generic team/dept, not a person
_NON_PERSON = {"department", "team", "management", "hr", "people", "talent", "recruiting",
               "careers", "jobs", "group", "office", "staff", "resources", "human", "inc",
               "llc", "corp", "company", "the", "support", "admin", "info"}


def _clean_name(seg):
    seg = re.sub(r"\b(on LinkedIn|LinkedIn|\| LinkedIn|- LinkedIn|profiles?|profile)\b", "", seg, flags=re.I)
    seg = re.sub(r"[|•·–—].*$", "", seg)
    seg = re.sub(r"\(.*?\)", "", seg).strip(" -,·|")
    # drop trailing creds
    seg = re.sub(r",?\s*(PhD|MBA|CIR|PHR|SHRM.*)$", "", seg, flags=re.I).strip()
    return seg


def classify_title(text):
    t = (text or "").lower()
    for kind, kw in _ALL_TITLE_KW:
        if kw in t:
            return kind
    return None


def extract_person(result, company):
    """From one search result, pull (name, title, kind, linkedin_url, source, context)
    or None if it isn't clearly a person with a hiring-relevant title."""
    url = result.get("url", "") or ""
    title_line = result.get("title", "") or ""
    snippet = result.get("snippet", "") or ""
    host = re.search(r"https?://([^/]+)", url)
    host = host.group(1).lower() if host else ""

    is_linkedin = "linkedin.com/in" in url
    is_aggregator = any(h in host for h in AGGREGATOR_HOSTS)
    if not (is_linkedin or is_aggregator):
        return None  # only trust person-profile sources for names

    # Title line usually: "Name - Job Title - Company | LinkedIn"
    parts = re.split(r"\s+[-–—|]\s+", title_line)
    name = _clean_name(parts[0]) if parts else ""
    if not _NAME_RE.match(name):
        return None
    toks = [t.lower() for t in name.split()]
    if any(t in _NON_PERSON for t in toks):
        return None  # "Google HR Department", "Mirage Management Team", etc.

    # find a hiring-relevant title from the rest of the title line + snippet
    rest = " ".join(parts[1:]) + " " + snippet
    kind = classify_title(rest)
    if kind is None:
        return None  # not a hiring-relevant person
    # human-readable title = the segment that carried the keyword, else first non-name part
    role_title = ""
    for seg in parts[1:]:
        if classify_title(seg):
            role_title = seg.strip(); break
    if not role_title:
        role_title = parts[1].strip() if len(parts) > 1 else kind

    return {
        "name": name,
        "title": role_title[:80],
        "kind": kind,
        "linkedin_url": url if is_linkedin else "",
        "source": "linkedin" if is_linkedin else host,
        "context": snippet[:240],
    }


# ─────────────────────────── company domain resolver ───────────────────────────

COMMON_TLDS = [".com", ".ai", ".io", ".co", ".dev", ".tech", ".app"]
COMPANY_SUFFIXES = {"inc", "llc", "ltd", "corp", "co", "the", "company", "group", "labs",
                    "technologies", "technology", "tech", "solutions", "consulting", "services",
                    "systems", "global", "international", "partners", "ventures", "studio"}
_DOMAIN_CACHE = {}


def _slug(company):
    return re.sub(r"[^a-z0-9]", "", (company or "").lower())


def _domain_slugs(company):
    """Company → candidate slugs for domain guessing, suffix-stripped.
    'Docker, Inc' → ['docker','dockerinc'];  'Tata Consultancy Services (TCS)' → ['tataconsultancyservices','tcs',...]."""
    base = re.sub(r"\(.*?\)", " ", company or "")
    words = [w for w in re.sub(r"[^a-z0-9 ]", " ", base.lower()).split()]
    core = [w for w in words if w not in COMPANY_SUFFIXES] or words
    cands = []
    # full name first (most specific — '10alabs' beats '10a'), then suffix-stripped fallbacks
    for form in ("".join(words), "".join(core), core[0] if core else ""):
        if form and form not in cands:
            cands.append(form)
    # acronym in parens, e.g. (TCS)
    ac = re.search(r"\(([A-Za-z]{2,6})\)", company or "")
    if ac:
        a = ac.group(1).lower()
        if a not in cands:
            cands.append(a)
    return cands


def resolve_domain(company, provider, brave_key):
    """Best-effort primary email domain for a company. Guess TLDs + MX-verify,
    then fall back to a search for the official site."""
    if company in _DOMAIN_CACHE:
        return _DOMAIN_CACHE[company]
    dom = None
    for slug in _domain_slugs(company):
        for tld in COMMON_TLDS:
            cand = slug + tld
            if mx_hosts(cand):
                dom = cand; break
        if dom:
            break
    if not dom:
        core_tokens = set(re.sub(r"[^a-z0-9 ]", " ", (company or "").lower()).split()) - COMPANY_SUFFIXES
        try:
            for res in run_search(f'"{company}" official website', provider, brave_key)[:6]:
                h = re.search(r"https?://(?:www\.)?([^/]+)", res.get("url", ""))
                if not h:
                    continue
                host = h.group(1).lower()
                skip = ("linkedin", "twitter", "x.com", "facebook", "crunchbase", "github",
                        "wikipedia", "wikidata", "glassdoor", "indeed", "youtube", "bloomberg",
                        "medium.com", "startup.jobs", "builtin", "levels.fyi", "gesi.org",
                        ".gov", ".edu") + AGGREGATOR_HOSTS
                if any(s in host for s in skip):
                    continue
                # require the domain's second-level label to share a token with the company name,
                # so we don't grab an unrelated site that merely mentions the company.
                sld = host.split(".")[-2] if host.count(".") >= 1 else host
                if core_tokens and not any(t in sld or sld in t for t in core_tokens if len(t) >= 3):
                    continue
                if mx_hosts(host):
                    dom = host; break
        except SearchError:
            pass
    _DOMAIN_CACHE[company] = dom
    return dom


# ─────────────────────────── email attach + verify ───────────────────────────

def catch_all(domain, mx, sender):
    try:
        with smtplib.SMTP(mx, 25, timeout=12) as s:
            s.ehlo_or_helo_if_needed(); s.mail(sender)
            code, _ = s.rcpt(f"zz-nobody-9713xk@{domain}")
            return code == 250
    except Exception:
        return None


def verify_person_email(name, domain, size_tier, sender="verify@example.com", max_variants=6):
    """Single connection, catch-all check, probe top variants, early-exit on 250.

    Returns (confirmed_email, status, detail, candidates):
      - status 'verified'   → confirmed_email is a real SMTP-250 address; candidates=[]
      - status 'catch-all'  → domain accepts anything; confirmed_email=None; candidates=ranked guesses
      - status 'unverified' → probe filtered / no 250; confirmed_email=None; candidates=ranked guesses
      - status 'invalid'    → no MX / no parseable name; confirmed_email=None; candidates=[]
    The user asked: only surface CONFIRMED emails; otherwise hand back the
    permutation list to try manually.
    """
    mx = mx_hosts(domain)
    if not mx:
        return None, "invalid", "no-MX", []
    cands = permutations_for(name, domain, size_tier)[:max_variants]
    if not cands:
        return None, "invalid", "no-name", []
    cand_emails = [c["email"] for c in cands]
    ca = catch_all(domain, mx[0], sender)
    if ca is True:
        return None, "catch-all", "domain accepts any address — cannot confirm", cand_emails
    try:
        with smtplib.SMTP(mx[0], 25, timeout=12) as s:
            s.ehlo_or_helo_if_needed(); s.mail(sender)
            for c in cands:
                code, _ = s.rcpt(c["email"])
                if code == 250:
                    return c["email"], "verified", c["pattern"], []   # confirmed — no need for candidates
                time.sleep(0.5)
            return None, "unverified", "no variant returned 250 (probe filtered or none exist)", cand_emails
    except Exception as e:
        return None, "unverified", f"probe-error:{type(e).__name__}", cand_emails


# ─────────────────────────── job source ───────────────────────────

SUPPORTED_ATS_HOSTS = ("greenhouse.io", "ashbyhq.com", "lever.co", "workable.com", "smartrecruiters.com")


def _is_real_company_url(url):
    """A direct company/ATS URL (not a LinkedIn/Indeed aggregator staffing repost)."""
    host = re.search(r"https?://([^/]+)", (url or "").lower())
    if not host:
        return False
    h = host.group(1)
    if any(a in h for a in ("linkedin.com", "indeed.com", "glassdoor.com", "ziprecruiter.com")):
        return False
    return True


def load_latest_jobs(data_js, session_id=None, order="ats-first"):
    txt = Path(data_js).read_text(encoding="utf-8")
    m = re.search(r"window\.JOB_SESSIONS\s*=\s*(.*?);?\s*$", txt, flags=re.S)
    if not m:
        return None, []
    sessions = json.loads(m.group(1))
    if not sessions:
        return None, []
    sess = next((s for s in sessions if s["id"] == session_id), sessions[0])
    jobs = sess.get("jobs", [])
    if order == "ats-first":
        # real-company/direct-ATS jobs first (skip LinkedIn staffing-agency reposts to the back),
        # then by score. These are the companies actually worth emailing.
        jobs = sorted(jobs, key=lambda j: (0 if _is_real_company_url(j.get("url")) else 1,
                                           -(j.get("score") or 0)))
    else:
        jobs = sorted(jobs, key=lambda j: -(j.get("score") or 0))
    return sess, jobs


# ─────────────────────────── scoring ───────────────────────────

KIND_WEIGHT = {"recruiter": 30, "people": 26, "hiring-manager": 22, "founder": 20, "engineer": 10}
# Confirmed email is the deliverable — weight it hard; unconfirmed guesses get little.
EMAIL_WEIGHT = {"verified": 35, "catch-all": 8, "unverified": 6, "invalid": 0, None: 0}


def score_contact(c, job):
    pts = 0
    pts += KIND_WEIGHT.get(c["kind"], 8)               # role proximity to hiring (max 30)
    pts += EMAIL_WEIGHT.get(c.get("email_status"), 0)   # confirmed deliverability (max 35)
    if c.get("linkedin_url"):
        pts += 12                                        # reachable on LinkedIn too
    jt = (job.get("title") or "").lower()
    if any(k in (c.get("title") or "").lower() for k in ("ai", "ml", "machine learning", "technical", "engineering")):
        pts += 8                                          # title aligned to eng hiring
    pts += 12 if (job.get("score") or 0) >= 70 else 6    # strength of the underlying job match
    return max(0, min(100, pts))


# ─────────────────────────── helpers ───────────────────────────

def stable_id(*parts):
    return hashlib.sha256("||".join((p or "").lower() for p in parts).encode()).hexdigest()[:16]


def guess_github_org(company, domain):
    """Cheap guesses for a company's GitHub org login."""
    cands = [_slug(company)]
    if domain:
        cands.append(domain.split(".")[0])
    seen, out = set(), []
    for c in cands:
        if c and c not in seen:
            seen.add(c); out.append(c)
    return out


# ─────────────────────────── main ───────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", default=datetime.date.today().isoformat())
    ap.add_argument("--label", default="us-ai")
    ap.add_argument("--provider", choices=["brave", "searxng"], default="brave")
    ap.add_argument("--target", type=int, default=50, help="jobs-with-contacts to collect (backfills to hit it)")
    ap.add_argument("--max-jobs", type=int, default=120, help="hard cap on jobs scanned while backfilling")
    ap.add_argument("--contacts-per-job", type=int, default=2)
    ap.add_argument("--size-tier", type=int, default=120, help="assumed headcount for email-pattern weighting")
    ap.add_argument("--no-verify", action="store_true", help="skip SMTP probe (MX-only grading)")
    ap.add_argument("--data-js", default="E:/_Resume-Curator/job_search/jobs_ui/data.js")
    ap.add_argument("--html-data", default="E:/_Resume-Curator/job_search/jobs_ui/hires.js")
    ap.add_argument("--state", default=os.path.expanduser("~/.job_search/state.json"))
    ap.add_argument("--sessions-dir", default=os.path.expanduser("~/.job_search/sessions"))
    ap.add_argument("--session-id", default=None)
    ap.add_argument("--order", choices=["ats-first", "score"], default="ats-first",
                    help="ats-first = real-company/direct-ATS jobs before LinkedIn staffing reposts (default)")
    ap.add_argument("--ignore-seen", action="store_true",
                    help="don't dedup against seen_hire_ids (re-scan / after a fix)")
    ap.add_argument("--dry-run", action="store_true", help="print contacts, don't write hires.js/state")
    args = ap.parse_args()

    today = datetime.date.fromisoformat(args.today)
    brave_key = os.environ.get("BRAVE_API_KEY") or os.environ.get("BRAVE_SEARCH_API_KEY")
    key_file = Path(os.path.expanduser("~/.job_search/brave_key.txt"))
    if not brave_key and key_file.exists():
        brave_key = key_file.read_text(encoding="utf-8").strip()

    sess, jobs = load_latest_jobs(args.data_js, args.session_id, args.order)
    if not jobs:
        print("no jobs in latest session; run /job-search first", file=sys.stderr); sys.exit(1)
    print(f"[hire-crawl] source session={sess['id']} jobs={len(jobs)} order={args.order} "
          f"provider={args.provider} target={args.target}", file=sys.stderr)

    state = json.loads(Path(os.path.expanduser(args.state)).read_text(encoding="utf-8"))
    seen_hire = set(state.get("seen_hire_ids", []))

    contacts = []          # flat list of contact records
    jobs_with_contacts = 0
    scanned = 0
    search_calls = 0

    tier_order = ["recruiter", "people", "hiring-manager", "founder"]

    for job in jobs:
        if jobs_with_contacts >= args.target or scanned >= args.max_jobs:
            break
        scanned += 1
        company = (job.get("company") or "").strip()
        if not company:
            continue
        location = job.get("location") or ""
        role = job.get("title") or ""
        domain = resolve_domain(company, args.provider, brave_key)

        found = []
        seen_names = set()

        # tiers 1-4 via search
        for tier in tier_order:
            if len(found) >= args.contacts_per_job:
                break
            kws = TITLE_KEYWORDS[tier]
            or_clause = " OR ".join(f'"{k}"' for k in kws[:4])
            q = f'"{company}" ({or_clause})'
            if tier in ("hiring-manager",) and role:
                q += f' {role.split("(")[0].strip()[:30]}'
            try:
                results = run_search(q, args.provider, brave_key)
                search_calls += 1
                if args.provider == "brave":
                    time.sleep(1.05)  # free tier: 1 query/sec
            except SearchError as e:
                print(f"  ! search failed [{company}/{tier}]: {e}", file=sys.stderr)
                continue
            for res in results:
                p = extract_person(res, company)
                if not p:
                    continue
                nm = p["name"].lower()
                if nm in seen_names:
                    continue
                seen_names.add(nm)
                p["company"] = company
                found.append(p)
                if len(found) >= args.contacts_per_job:
                    break

        # tier 5 (last resort): engineers via GitHub commit emails — only if nothing found
        if not found and domain:
            for org in guess_github_org(company, domain):
                gh = github_org_emails(org)
                gh_same = [g for g in gh if g["email"].endswith("@" + domain)]
                for g in gh_same[:args.contacts_per_job]:
                    found.append({
                        "name": g.get("name") or g["email"].split("@")[0],
                        "title": "Engineer (GitHub commit author)",
                        "kind": "engineer",
                        "linkedin_url": "",
                        "source": "github",
                        "context": f"Public commit author in {org}/{g.get('repo','')}",
                        "company": company,
                        "email": g["email"], "email_status": "verified", "email_source": "github-commit",
                    })
                if found:
                    break

        if not found:
            continue

        # attach emails for search-found people (GitHub ones already have a confirmed email)
        for p in found:
            candidates = []
            if p.get("email"):
                # GitHub commit email — exact/confirmed
                p["email_status"] = p.get("email_status", "verified")
                p["email_source"] = p.get("email_source", "github-commit")
            elif domain:
                if args.no_verify:
                    cands = permutations_for(p["name"], domain, args.size_tier)
                    candidates = [c["email"] for c in cands[:6]]
                    p["email"] = None
                    p["email_status"] = "unverified"
                    p["email_source"] = "guess"
                else:
                    email, status, detail, candidates = verify_person_email(p["name"], domain, args.size_tier)
                    p["email"] = email                       # confirmed-only (None unless a real 250)
                    p["email_status"] = status
                    p["email_source"] = "smtp-verified" if status == "verified" else "guess-candidates"
            else:
                p["email"] = None; p["email_status"] = "invalid"; p["email_source"] = "no-domain"

            rec = {
                "kind": p["kind"], "name": p["name"], "title": p["title"], "company": company,
                "linkedin_url": p.get("linkedin_url") or "", "post_url": None,
                "location": location or "United States",
                "hiring_for": role, "job_url": job.get("url"), "job_score": job.get("score"),
                "context": p.get("context", ""), "intent": None, "niche": None,
                "email": p.get("email"),                     # ONLY a confirmed address, else null
                "email_status": p.get("email_status"),
                "email_source": p.get("email_source"),
                "email_candidates": candidates,              # ranked guesses to try when unconfirmed
                "domain": domain, "source": p.get("source"),
                "_at": None,
                "_id": stable_id(p["name"], company, p.get("email") or p.get("linkedin_url") or ""),
            }
            rec["score"] = score_contact(rec, job)
            contacts.append(rec)

        jobs_with_contacts += 1
        print(f"  [{jobs_with_contacts}/{args.target}] {company}: {len(found)} contact(s) "
              f"(scanned {scanned})", file=sys.stderr)

    # dedup vs seen + within-run; rank
    fresh, ids_run = [], set()
    dropped = {"already-seen": 0, "duplicate-in-run": 0}
    for c in sorted(contacts, key=lambda x: -x["score"]):
        if c["_id"] in seen_hire and not args.ignore_seen:
            dropped["already-seen"] += 1; continue
        if c["_id"] in ids_run:
            dropped["duplicate-in-run"] += 1; continue
        ids_run.add(c["_id"]); fresh.append(c)
    for i, c in enumerate(fresh, 1):
        c["rank"] = i

    # summary counts
    n_verified = sum(1 for c in fresh if c.get("email_status") == "verified")
    n_candidates = sum(1 for c in fresh if c.get("email_candidates"))
    print(f"\n[hire-crawl] contacts={len(fresh)}  confirmed-email={n_verified}  "
          f"with-candidates={n_candidates}  jobs_with_contacts={jobs_with_contacts}  "
          f"search_calls={search_calls}", file=sys.stderr)

    if args.dry_run:
        for c in fresh[:40]:
            if c.get("email"):
                em = f"{c['email']}  ✓CONFIRMED"
            elif c.get("email_candidates"):
                em = f"try: {', '.join(c['email_candidates'][:3])} …({c['email_status']})"
            else:
                em = f"(no email — {c.get('email_status')})"
            print(f"  {c['score']:3d} [{c['kind']:13s}] {c['name']:20s} {c['company'][:20]:22s} {em}")
        return

    # write hires.js session
    session = {
        "id": f"{today.isoformat()}_{args.label}",
        "date": today.isoformat(),
        "label": args.label,
        "raw_total": len(contacts),
        "after_dedup": len(fresh),
        "verified_email": n_verified,
        "with_candidates": n_candidates,
        "jobs_scanned": scanned,
        "jobs_with_contacts": jobs_with_contacts,
        "source_job_session": sess["id"],
        "drop_log": dropped,
        "people": fresh,
    }
    _write_hires_js(args.html_data, session)

    # MD backup
    os.makedirs(args.sessions_dir, exist_ok=True)
    md = os.path.join(args.sessions_dir, f"hires_{today.isoformat()}_{args.label}.md")
    _write_md(md, session)

    # state
    state.setdefault("seen_hire_ids", [])
    state["seen_hire_ids"] = sorted(set(state["seen_hire_ids"]) | ids_run)
    state.setdefault("hire_session_log", []).append({
        "date": today.isoformat(), "label": args.label, "provider": args.provider,
        "source_job_session": sess["id"], "contacts": len(fresh),
        "verified_email": n_verified, "with_candidates": n_candidates,
        "jobs_with_contacts": jobs_with_contacts,
    })
    tmp = args.state + ".tmp"
    Path(tmp).write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, args.state)

    print(f"\n✅ hire-crawl done: {len(fresh)} contacts — {n_verified} with a CONFIRMED email, "
          f"{n_candidates} with candidate lists to try. Open jobs_ui/hires.html")


def _write_hires_js(path, session):
    sessions = []
    if os.path.exists(path):
        try:
            content = Path(path).read_text(encoding="utf-8").strip()
            m = re.search(r"window\.HIRE_SESSIONS\s*=\s*(.*?);?\s*$", content, flags=re.S)
            if m and m.group(1).strip():
                sessions = json.loads(m.group(1))
        except Exception as e:
            print(f"warning: could not parse hires.js ({e}); starting fresh", file=sys.stderr)
    sessions = [s for s in sessions if s.get("id") != session["id"]]
    sessions.insert(0, session)
    tmp = path + ".tmp"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("window.HIRE_SESSIONS = ")
        json.dump(sessions, f, ensure_ascii=False, indent=2)
        f.write(";\n")
    os.replace(tmp, path)


def _write_md(path, session):
    L = [f"# Hire Search — {session['label']} — {session['date']}", ""]
    L.append(f"**{session['after_dedup']} contacts** — {session['verified_email']} with a CONFIRMED email, "
             f"{session.get('with_candidates', 0)} with candidate lists to try — across "
             f"{session['jobs_with_contacts']} jobs.")
    L.append(f"Source job session: `{session['source_job_session']}`")
    L.append("")
    for c in session["people"]:
        st = c.get("email_status") or ""
        li = f" · [LinkedIn]({c['linkedin_url']})" if c.get("linkedin_url") else ""
        L.append(f"### #{c['rank']} · {c['score']}/100 · {c['kind']}")
        L.append(f"**{c['name']}** — *{c['title']}* — **{c['company']}**{li}")
        if c.get("email"):
            L.append(f"  ✉ **`{c['email']}`**  ✓ CONFIRMED (SMTP 250)  ·  hiring for: {c.get('hiring_for') or '—'}")
        elif c.get("email_candidates"):
            L.append(f"  ✉ not confirmed ({st}) — try: " +
                     ", ".join(f"`{e}`" for e in c["email_candidates"][:5]))
            L.append(f"     hiring for: {c.get('hiring_for') or '—'}")
        else:
            L.append(f"  ✉ no email ({st})  ·  hiring for: {c.get('hiring_for') or '—'}")
        if c.get("context"):
            L.append(f"  > {c['context'][:200]}")
        L.append("")
    Path(path).write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
