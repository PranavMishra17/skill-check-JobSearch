"""crawl_all.py — multi-source job crawler.

Runs JobSpy (broadened) + GitHub repos (SimplifyJobs/New-Grad-Positions,
speedyapply/2026-AI-College-Jobs) + Arbeitnow API, normalises every row to the
same Apify-shape JSON, merges + URL-dedupes, and writes a single
{"items": [...]} file the existing render_results.py consumes unchanged.

Sources are additive — failure in one source doesn't block the others.

Usage:
    python crawl_all.py --window-days 3 --output ~/.job_search/raw_jobs/2026-06-08_3d.json
"""
import argparse, json, math, os, re, sys, urllib.request, urllib.error, hashlib, datetime
from pathlib import Path

try:
    from jobspy import scrape_jobs
except ImportError:
    scrape_jobs = None

# ───────────────────────── BROADENED SEARCH SCOPE ─────────────────────────

JOBSPY_TERMS = [
    "AI Engineer", "Machine Learning Engineer", "ML Engineer",
    "LLM Engineer", "Generative AI Engineer", "Deep Learning Engineer",
    "Founding Engineer", "Forward Deployed Engineer",
    "Applied AI Engineer", "Applied AI",
    "AI Software Engineer", "AI Infrastructure Engineer",
    "MLOps Engineer", "Research Engineer", "AI Research Engineer",
    "Software Engineer AI", "Software Engineer ML",
]

JOBSPY_SITES_DEFAULT = ["indeed", "google", "glassdoor"]  # LinkedIn opt-in (slow); ZipRecruiter excluded — 429s aggressively

# Loosened pre-filter — only obvious senior/non-engineering titles.
# render_results.py does the proper title-scope filtering.
TITLE_EXCLUDE = [
    "senior ", "sr.", " sr ", "lead ", "staff ", "principal ",
    "director", " vp ", "vice president", "head of", " manager",
    "chief ", " sales ", " marketing ", "recruiter", " designer",
    "front-end developer", "frontend developer", "front end developer",
]

# GitHub repos to scrape
GITHUB_REPOS = [
    {
        "name": "SimplifyJobs/New-Grad-Positions",
        "kind": "simplify_json",
        "url": "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/.github/scripts/listings.json",
    },
    {
        "name": "speedyapply/2026-AI-College-Jobs",
        "kind": "speedyapply_md",
        "url": "https://raw.githubusercontent.com/speedyapply/2026-AI-College-Jobs/main/NEW_GRAD_USA.md",
    },
    {
        "name": "speedyapply/2026-SWE-College-Jobs",
        "kind": "speedyapply_md",
        "url": "https://raw.githubusercontent.com/speedyapply/2026-SWE-College-Jobs/main/NEW_GRAD_USA.md",
    },
    {
        "name": "jobright-ai/2026-Software-Engineer-New-Grad",
        "kind": "speedyapply_md",  # same format
        "url": "https://raw.githubusercontent.com/jobright-ai/2026-Software-Engineer-New-Grad/master/README.md",
    },
]

# AI/ML keywords used to filter generic feeds (Arbeitnow, generic-SWE repos)
AI_TITLE_KEYWORDS = [
    "ai", "ml", "machine learning", "llm", "deep learning", "agentic",
    "data scientist", "research engineer", "applied scientist", "mlops",
    "generative", "founding engineer", "forward deployed",
]

# Recruitment-agency heuristic
AGENCY_HINTS = ("staffing", "recruiting", "recruitment", "talent group", "talent partners",
                "executive search", "consultants", "consulting partners")

JOBTYPE_MAP = {
    "fulltime": "FULL_TIME", "full-time": "FULL_TIME", "full_time": "FULL_TIME",
    "parttime": "PART_TIME", "part-time": "PART_TIME",
    "contract": "CONTRACTOR", "internship": "INTERN", "intern": "INTERN",
    "temporary": "TEMPORARY",
}

YOE_RE = re.compile(r"(\d{1,2})\s*\+?\s*(?:to|-|–)?\s*\d{0,2}\s*\+?\s*years?", re.I)
SENIORITY_TITLE_RE = re.compile(r"\b(senior|sr\.?|lead|staff|principal|director|vp|head\s+of|manager|chief)\b", re.I)


# ───────────────────────── shared helpers ─────────────────────────

def _nan(v):
    try: return v is None or (isinstance(v, float) and math.isnan(v))
    except Exception: return v is None

def _str(v):
    if _nan(v): return None
    s = str(v).strip()
    return s if s else None

def stable_id(company, title, url):
    return hashlib.sha256(f"{(company or '').lower()}{(title or '').lower()}{url or ''}".encode()).hexdigest()[:16]

def infer_experience_level(title, description):
    title_l = (title or "").lower()
    desc_l = (description or "").lower()
    if SENIORITY_TITLE_RE.search(title_l): return "5-10"
    if any(w in title_l for w in ["entry", "junior", "new grad", "associate", "intern", " i ", " ii", " iii"]):
        return "0-2"
    if description:
        years = [int(m.group(1)) for m in YOE_RE.finditer(description) if int(m.group(1)) <= 20]
        if years:
            top = max(years)
            if top >= 10: return "10+"
            if top >= 5:  return "5-10"
            if top >= 2:  return "2-5"
            return "0-2"
    return "2-5"

def infer_work_arrangement(is_remote, description):
    desc_l = (description or "").lower()
    if is_remote: return "Remote OK"
    if "hybrid" in desc_l: return "Hybrid"
    if "fully remote" in desc_l or "100% remote" in desc_l or "remote-first" in desc_l:
        return "Remote OK"
    return "On-site"

def is_agency(company):
    if not company: return False
    lo = company.lower()
    return any(t in lo for t in AGENCY_HINTS)

def title_in_ai_scope(title):
    if not title: return False
    t = title.lower()
    return any(k in t for k in AI_TITLE_KEYWORDS) or "engineer" in t or "scientist" in t

def title_should_drop(title):
    if not title: return True
    t = title.lower()
    return any(x in t for x in TITLE_EXCLUDE)


def fetch_url(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "skill-check-JobSearch/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


# ───────────────────────── source: JOBSPY ─────────────────────────

def jobspy_row_to_item(row):
    site = _str(row.get("site")) or ""
    company = _str(row.get("company")) or ""
    title = _str(row.get("title")) or ""
    url = _str(row.get("job_url")) or _str(row.get("job_url_direct")) or ""
    description = _str(row.get("description")) or ""

    city = _str(row.get("city"))
    state = _str(row.get("state"))
    country = _str(row.get("country")) or "USA"
    loc_str = ", ".join([p for p in [city, state, country] if p])
    locs = [loc_str] if loc_str else []

    dp = row.get("date_posted")
    if dp is None or _nan(dp): dp = None
    elif hasattr(dp, "isoformat"): dp = dp.isoformat()
    else: dp = str(dp).strip() or None

    s_min = row.get("min_amount")
    s_max = row.get("max_amount")
    s_min = float(s_min) if (s_min is not None and not _nan(s_min)) else None
    s_max = float(s_max) if (s_max is not None and not _nan(s_max)) else None
    interval = _str(row.get("interval"))
    s_unit = "YEAR" if interval == "yearly" else ("HOUR" if interval == "hourly" else None)
    currency = _str(row.get("currency")) or ("USD" if s_min else None)

    jt_raw = _str(row.get("job_type")) or "fulltime"
    emp_type = [JOBTYPE_MAP.get(jt_raw.lower().split(",")[0].strip(), "FULL_TIME")]

    country_full = "United States" if country.upper() in ("US","USA","UNITED STATES") else country

    return _build_item(
        company=company, title=title, url=url, description=description,
        locations=locs, country_full=country_full,
        is_remote=bool(row.get("is_remote")),
        source=f"jobspy:{site}",
        emp_type=emp_type,
        s_min=s_min, s_max=s_max, s_unit=s_unit, currency=currency,
        date_posted=dp,
        company_industry=_str(row.get("company_industry")),
    )


def crawl_jobspy_source(window_days, location, sites, terms, results_per_search, include_linkedin, country_indeed, verbose):
    if scrape_jobs is None:
        print("jobspy: not installed; skip", file=sys.stderr)
        return []
    if include_linkedin and "linkedin" not in sites:
        sites = sites + ["linkedin"]
    hours_old = max(1, window_days * 24)
    items = []
    seen_urls = set()
    excluded = 0
    raw_total = 0
    for i, term in enumerate(terms, 1):
        if verbose:
            print(f"  jobspy [{i}/{len(terms)}] '{term}'", file=sys.stderr)
        try:
            df = scrape_jobs(
                site_name=sites,
                search_term=term,
                google_search_term=f"{term} jobs in {location} since past {window_days} days",
                location=location,
                hours_old=hours_old,
                results_wanted=results_per_search,
                country_indeed=country_indeed,
                description_format="markdown",
                linkedin_fetch_description=("linkedin" in sites),
                enforce_annual_salary=True,
                job_type="fulltime",
                verbose=0,
            )
        except Exception as e:
            print(f"      ! '{term}' failed: {e}", file=sys.stderr)
            continue
        if df is None or len(df) == 0:
            continue
        raw_total += len(df)
        for _, row in df.iterrows():
            u = (row.get("job_url") or "").strip()
            if not u or u in seen_urls: continue
            seen_urls.add(u)
            t = (row.get("title") or "")
            if title_should_drop(t):
                excluded += 1; continue
            items.append(jobspy_row_to_item(row.to_dict()))
    print(f"  jobspy: {len(items)} kept (raw {raw_total}, excluded {excluded}, dedupd {raw_total - len(seen_urls)})", file=sys.stderr)
    return items


# ───────────────────────── source: GITHUB simplify JSON ─────────────────────────

def crawl_simplify_json(repo_meta, window_days, verbose):
    """SimplifyJobs/New-Grad-Positions style listings.json."""
    items = []
    try:
        raw = fetch_url(repo_meta["url"], timeout=60)
        data = json.loads(raw)
    except Exception as e:
        print(f"  github [{repo_meta['name']}]: fetch failed: {e}", file=sys.stderr)
        return []

    cutoff = datetime.datetime.now().timestamp() - window_days * 86400
    excluded = 0
    out_of_scope = 0
    inactive = 0
    too_old = 0
    for entry in data:
        if not entry.get("active", True) or not entry.get("is_visible", True):
            inactive += 1; continue
        dp = entry.get("date_posted") or entry.get("date_updated") or 0
        if dp and dp < cutoff:
            too_old += 1; continue
        title = entry.get("title") or ""
        if title_should_drop(title):
            excluded += 1; continue
        if not title_in_ai_scope(title):
            out_of_scope += 1; continue

        company = entry.get("company_name") or ""
        url = entry.get("url") or ""
        locations_list = entry.get("locations") or []
        loc_str = ", ".join(locations_list[:1]) if locations_list else None
        locs = [loc_str] if loc_str else []
        date_iso = datetime.datetime.fromtimestamp(dp).isoformat() if dp else None

        items.append(_build_item(
            company=company, title=title, url=url, description=title,
            locations=locs, country_full="United States",
            is_remote=("remote" in (loc_str or "").lower()),
            source=f"github:{repo_meta['name']}",
            emp_type=["FULL_TIME"],
            s_min=None, s_max=None, s_unit=None, currency=None,
            date_posted=date_iso,
        ))
    print(f"  github [{repo_meta['name']}]: {len(items)} kept "
          f"(inactive {inactive}, too-old {too_old}, excluded {excluded}, out-of-scope {out_of_scope})",
          file=sys.stderr)
    return items


# ───────────────────────── source: GITHUB speedyapply markdown ─────────────────────────

_MD_ROW_RE = re.compile(r"^\|.+\|.+\|.+\|.+\|.+\|\s*$")  # at least 5 cells (Company|Role|Loc|Apply|Age)
_MD_DIVIDER_RE = re.compile(r"^\|\s*[:-]+\s*\|")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_HREF_RE = re.compile(r'href="([^"]+)"')
_STRONG_RE = re.compile(r"<strong>(.*?)</strong>", re.I | re.S)
_AGE_RE = re.compile(r"^(\d{1,3})\s*([dhmwy])\s*$", re.I)

def _strip_html(s):
    return _HTML_TAG_RE.sub("", s or "").strip()

def _parse_age_to_days(age_str):
    if not age_str: return None
    s = age_str.strip().lower()
    m = _AGE_RE.match(s)
    if not m: return None
    n = int(m.group(1))
    unit = m.group(2)
    if unit == "d": return n
    if unit == "h": return max(0, n // 24)
    if unit == "w": return n * 7
    if unit == "m": return n * 30
    if unit == "y": return n * 365
    return None

def crawl_speedyapply_md(repo_meta, window_days, verbose):
    """speedyapply/2026-AI-College-Jobs style markdown table."""
    items = []
    try:
        md = fetch_url(repo_meta["url"], timeout=60)
    except Exception as e:
        print(f"  github [{repo_meta['name']}]: fetch failed: {e}", file=sys.stderr)
        return []

    excluded = 0; too_old = 0; out_of_scope = 0
    last_company = None  # repos often elide repeat companies with "↳"
    for line in md.splitlines():
        if not _MD_ROW_RE.match(line) or _MD_DIVIDER_RE.match(line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 5:
            continue

        # Column-count-agnostic: Apply is always second-to-last, Age is always last.
        # Layouts: 5 cells = Company|Role|Loc|Apply|Age
        #          6 cells = Company|Role|Loc|Salary|Apply|Age
        company_html, position, location = cells[0], cells[1], cells[2]
        age = cells[-1]
        posting_html = cells[-2]
        salary = cells[3] if len(cells) >= 6 else ""

        # Company: "↳" means "same as previous"
        if company_html.strip() in {"↳", "&#8627;", ""}:
            company = last_company
        else:
            sm = _STRONG_RE.search(company_html)
            company = (sm.group(1).strip() if sm else _strip_html(company_html)) or None
            last_company = company

        title = _strip_html(position).strip()
        if title_should_drop(title):
            excluded += 1; continue
        if not title_in_ai_scope(title):
            out_of_scope += 1; continue

        # Apply URL: prefer Apply column href, fall back to company href
        href_match = _HREF_RE.search(posting_html) or _HREF_RE.search(company_html)
        url = href_match.group(1) if href_match else ""

        age_days = _parse_age_to_days(age)
        if age_days is not None and age_days > window_days:
            too_old += 1; continue
        date_iso = (datetime.datetime.now() - datetime.timedelta(days=age_days or 0)).date().isoformat() if age_days is not None else None

        loc_clean = _strip_html(location).strip()
        country_full = "United States" if any(x in loc_clean.lower() for x in ["us", "usa", "united states"]) else "United States"
        locs = [loc_clean] if loc_clean else []
        is_remote = "remote" in loc_clean.lower()

        # Salary parse: "$172k/yr"
        s_min = None
        if salary:
            sal_m = re.search(r"\$?\s*(\d+(?:\.\d+)?)\s*([kK]?)", _strip_html(salary))
            if sal_m:
                try:
                    v = float(sal_m.group(1))
                    if "k" in sal_m.group(2).lower(): v *= 1000
                    s_min = v
                except: pass

        items.append(_build_item(
            company=company or "", title=title, url=url, description=title,
            locations=locs, country_full=country_full,
            is_remote=is_remote,
            source=f"github:{repo_meta['name']}",
            emp_type=["FULL_TIME"],
            s_min=s_min, s_max=None, s_unit="YEAR" if s_min else None, currency="USD" if s_min else None,
            date_posted=date_iso,
        ))
    print(f"  github [{repo_meta['name']}]: {len(items)} kept (excluded {excluded}, too-old {too_old}, out-of-scope {out_of_scope})", file=sys.stderr)
    return items


# ───────────────────────── source: ARBEITNOW ─────────────────────────

def crawl_arbeitnow(window_days, verbose):
    items = []
    try:
        raw = fetch_url("https://www.arbeitnow.com/api/job-board-api", timeout=30)
        payload = json.loads(raw)
    except Exception as e:
        print(f"  arbeitnow: fetch failed: {e}", file=sys.stderr)
        return []

    cutoff = datetime.datetime.now().timestamp() - window_days * 86400
    excluded = 0; too_old = 0; out_of_scope = 0
    for j in payload.get("data", []):
        created = j.get("created_at") or 0
        if created and created < cutoff:
            too_old += 1; continue
        title = j.get("title") or ""
        if title_should_drop(title):
            excluded += 1; continue
        if not title_in_ai_scope(title):
            out_of_scope += 1; continue

        company = j.get("company_name") or ""
        url = j.get("url") or ""
        description = j.get("description") or ""
        loc = j.get("location") or ""
        is_remote = bool(j.get("remote"))
        date_iso = datetime.datetime.fromtimestamp(created).isoformat() if created else None
        country_full = "United States" if any(x in loc.lower() for x in ["us", "usa", "united states"]) else (loc.split(",")[-1].strip() or "Other")

        items.append(_build_item(
            company=company, title=title, url=url, description=description,
            locations=[loc] if loc else [], country_full=country_full,
            is_remote=is_remote, source="arbeitnow",
            emp_type=["FULL_TIME"],
            s_min=None, s_max=None, s_unit=None, currency=None,
            date_posted=date_iso,
        ))
    print(f"  arbeitnow: {len(items)} kept (too-old {too_old}, excluded {excluded}, out-of-scope {out_of_scope})", file=sys.stderr)
    return items


# ───────────────────────── unified item builder ─────────────────────────

def _build_item(*, company, title, url, description, locations, country_full,
                is_remote, source, emp_type, s_min, s_max, s_unit, currency,
                date_posted, company_industry=None):
    return {
        "id": stable_id(company, title, url),
        "date_posted": date_posted,
        "title": title,
        "organization": company,
        "locations_derived": locations,
        "countries_derived": [country_full] if country_full else ["United States"],
        "remote_derived": bool(is_remote),
        "url": url,
        "source": source,
        "ai_employment_type": emp_type,
        "ai_experience_level": infer_experience_level(title, description),
        "ai_work_arrangement": infer_work_arrangement(is_remote, description),
        "ai_visa_sponsorship": None,
        "ai_salary_currency": currency,
        "ai_salary_minvalue": s_min,
        "ai_salary_maxvalue": s_max,
        "ai_salary_unittext": s_unit,
        "ai_key_skills": [],
        "ai_taxonomies_a": ["Technology", "Software"],
        "ai_core_responsibilities": (description or "")[:280] if description else None,
        "ai_requirements_summary": None,
        "description_text": description or title,
        "linkedin_org_employees": None,
        "linkedin_org_industry": company_industry,
        "linkedin_org_size": None,
        "linkedin_org_recruitment_agency_derived": is_agency(company),
        "linkedin_org_specialties": [],
        "linkedin_org_description": None,
    }


# ───────────────────────── orchestrator ─────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-days", type=int, required=True)
    ap.add_argument("--location", default="United States")
    ap.add_argument("--country-indeed", default="USA")
    ap.add_argument("--results-per-search", type=int, default=30)
    ap.add_argument("--output", required=True)
    ap.add_argument("--sites", nargs="+", default=JOBSPY_SITES_DEFAULT,
                    help="JobSpy sites. linkedin is opt-in via --include-linkedin.")
    ap.add_argument("--include-linkedin", action="store_true")
    ap.add_argument("--terms", nargs="+", default=None)
    ap.add_argument("--company", default=None,
                    help="Targeted single-company crawl — overrides --terms.")
    ap.add_argument("--no-jobspy", action="store_true")
    ap.add_argument("--no-github", action="store_true")
    ap.add_argument("--no-arbeitnow", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    verbose = not args.quiet
    terms = [args.company] if args.company else (args.terms or JOBSPY_TERMS)
    out_path = Path(os.path.expanduser(args.output))

    all_items = []

    # 1) JobSpy
    if not args.no_jobspy:
        all_items.extend(crawl_jobspy_source(
            window_days=args.window_days, location=args.location,
            sites=list(args.sites), terms=terms,
            results_per_search=args.results_per_search,
            include_linkedin=args.include_linkedin,
            country_indeed=args.country_indeed, verbose=verbose,
        ))

    # 2) GitHub repos
    if not args.no_github and not args.company:
        for repo in GITHUB_REPOS:
            try:
                if repo["kind"] == "simplify_json":
                    all_items.extend(crawl_simplify_json(repo, args.window_days, verbose))
                elif repo["kind"] == "speedyapply_md":
                    all_items.extend(crawl_speedyapply_md(repo, args.window_days, verbose))
            except Exception as e:
                print(f"  github {repo['name']}: {e}", file=sys.stderr)

    # 3) Arbeitnow
    if not args.no_arbeitnow and not args.company:
        try:
            all_items.extend(crawl_arbeitnow(args.window_days, verbose))
        except Exception as e:
            print(f"  arbeitnow: {e}", file=sys.stderr)

    # Cross-source dedup by URL, then by (company, normalised-title)
    seen_url = set()
    seen_key = set()
    final = []
    cross_dropped = 0
    for it in all_items:
        u = it.get("url") or ""
        if u and u in seen_url:
            cross_dropped += 1; continue
        ckey = ((it.get("organization") or "").lower().strip(),
                re.sub(r"[^a-z0-9]+", " ", (it.get("title") or "").lower()).strip())
        if ckey in seen_key:
            cross_dropped += 1; continue
        seen_url.add(u); seen_key.add(ckey)
        final.append(it)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"items": final, "totalItemCount": len(final)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"crawl_all: {len(final)} unique items ({cross_dropped} cross-source duplicates dropped) → {out_path}",
          file=sys.stderr)
    print(str(out_path))


if __name__ == "__main__":
    main()
