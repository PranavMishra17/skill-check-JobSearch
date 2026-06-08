"""crawl_jobspy.py — JobSpy crawler producing Apify-compatible JSON.

Replaces the Apify fantastic-jobs/career-site-job-listing-api actor.
Writes a JSON file with the same {"items": [...]} schema that render_results.py
already consumes, so no downstream changes are needed.

Sources (default): Indeed, Glassdoor, Google Jobs, ZipRecruiter.
LinkedIn is opt-in via --include-linkedin (rate-limited, slower).

Usage:
    python crawl_jobspy.py \\
        --window-days 7 \\
        --location "United States" \\
        --output ~/.job_search/raw_jobs/2026-06-07_7d.json
"""
import argparse, json, re, sys, datetime, math, os
from pathlib import Path

try:
    from jobspy import scrape_jobs
    import pandas as pd
except ImportError:
    print("ERROR: jobspy not installed. Run: pip install -U python-jobspy", file=sys.stderr)
    sys.exit(1)

# --- Search strategy
# Umbrella search terms (each one calls each site once). Kept small for speed and
# to avoid LinkedIn rate-limits; the broader title list lives in render_results.py
# as the post-scoring title scope.
DEFAULT_SEARCH_TERMS = [
    "AI Engineer",
    "Machine Learning Engineer",
    "LLM Engineer",
    "Founding Engineer",
    "Forward Deployed Engineer",
    "Applied AI Engineer",
]

# Hard pre-drop of obviously-out-of-scope titles before render_results.py sees them
TITLE_EXCLUDE = [
    "senior", "sr.", "sr ", "lead ", "staff ", "principal",
    "director", "vp ", "head of", "manager", "chief",
    "sales", "marketing", "recruiter", "designer",
    "frontend developer", "front-end developer", "front end developer",
    "data analyst",  # we want engineers, not analysts
]

JOBTYPE_MAP = {
    "fulltime": "FULL_TIME",
    "parttime": "PART_TIME",
    "contract": "CONTRACTOR",
    "internship": "INTERN",
    "temporary": "TEMPORARY",
    "per_diem": "PER_DIEM",
}

YOE_RE = re.compile(r"(\d{1,2})\s*\+?\s*(?:to|-|–)?\s*\d{0,2}\s*\+?\s*years?", re.I)
SENIORITY_TITLE_RE = re.compile(r"\b(senior|sr\.?|lead|staff|principal|director|vp|head\s+of|manager|chief)\b", re.I)

# Heuristic for recruitment-agency org names (Apify field name preserved for parity)
AGENCY_HINTS = (
    "staffing", "recruiting", "recruitment", "talent group", "talent partners",
    "consultants", "consulting partners", "executive search",
)


def _nan(v):
    try:
        return v is None or (isinstance(v, float) and math.isnan(v))
    except Exception:
        return v is None


def _str(v):
    if _nan(v):
        return None
    s = str(v).strip()
    return s if s else None


def stable_id(company, title, url):
    import hashlib
    return hashlib.sha256(f"{(company or '').lower()}{(title or '').lower()}{url or ''}".encode()).hexdigest()[:16]


def infer_experience_level(title, description):
    """Best-effort match for Apify's 0-2 / 2-5 / 5-10 / 10+ buckets."""
    title_l = (title or "").lower()
    desc_l = (description or "").lower()
    if SENIORITY_TITLE_RE.search(title_l):
        return "5-10"
    if any(w in title_l for w in ["entry", "junior", "new grad", "associate", "intern", "i ", " ii ", " iii"]):
        return "0-2"
    if description:
        years = [int(m.group(1)) for m in YOE_RE.finditer(description) if int(m.group(1)) <= 20]
        if years:
            top = max(years)
            if top >= 10: return "10+"
            if top >= 5:  return "5-10"
            if top >= 2:  return "2-5"
            return "0-2"
    # Mid-career safe default — render_results.py keeps 2-5 in scope
    return "2-5"


def infer_work_arrangement(is_remote, description):
    desc_l = (description or "").lower()
    if is_remote:
        return "Remote OK"
    if "hybrid" in desc_l:
        return "Hybrid"
    if "fully remote" in desc_l or "100% remote" in desc_l or "remote work" in desc_l:
        return "Remote OK"
    return "On-site"


def normalize_location_string(city, state, country):
    parts = [p for p in [_str(city), _str(state), _str(country)] if p]
    return ", ".join(parts) if parts else None


def row_to_apify_shape(row):
    """One JobSpy DataFrame row → one Apify-style item dict."""
    site = _str(row.get("site")) or ""
    company = _str(row.get("company")) or ""
    title = _str(row.get("title")) or ""
    url = _str(row.get("job_url")) or _str(row.get("job_url_direct")) or ""
    description = _str(row.get("description")) or ""

    # JobSpy splits location into city/state/country columns
    city = _str(row.get("city"))
    state = _str(row.get("state"))
    country = _str(row.get("country")) or "USA"
    loc_str = normalize_location_string(city, state, country)
    locs = [loc_str] if loc_str else []

    # Date posted — JobSpy returns a date or string
    dp = row.get("date_posted")
    if dp is None or _nan(dp):
        dp = None
    elif hasattr(dp, "isoformat"):
        dp = dp.isoformat()
    else:
        dp = str(dp).strip() or None

    # Salary block
    s_min = row.get("min_amount")
    s_max = row.get("max_amount")
    s_min = float(s_min) if (s_min is not None and not _nan(s_min)) else None
    s_max = float(s_max) if (s_max is not None and not _nan(s_max)) else None
    interval = _str(row.get("interval"))
    s_unit = "YEAR" if interval == "yearly" else ("HOUR" if interval == "hourly" else None)
    currency = _str(row.get("currency")) or ("USD" if s_min else None)

    # Employment type
    jt_raw = _str(row.get("job_type")) or "fulltime"
    jt_first = jt_raw.lower().split(",")[0].strip()
    emp_type = [JOBTYPE_MAP.get(jt_first, "FULL_TIME")]

    # Recruitment agency heuristic
    company_lower = company.lower()
    is_agency = any(t in company_lower for t in AGENCY_HINTS)

    # Map "country" → countries_derived (list, full name when possible)
    country_full = "United States" if country.upper() in ("US", "USA", "UNITED STATES") else country
    countries_derived = [country_full] if country_full else ["United States"]

    return {
        "id": stable_id(company, title, url),
        "date_posted": dp,
        "title": title,
        "organization": company,
        "locations_derived": locs,
        "countries_derived": countries_derived,
        "remote_derived": bool(row.get("is_remote")),
        "url": url,
        "source": f"jobspy:{site}",
        "ai_employment_type": emp_type,
        "ai_experience_level": infer_experience_level(title, description),
        "ai_work_arrangement": infer_work_arrangement(row.get("is_remote"), description),
        "ai_visa_sponsorship": None,
        "ai_salary_currency": currency,
        "ai_salary_minvalue": s_min,
        "ai_salary_maxvalue": s_max,
        "ai_salary_unittext": s_unit,
        "ai_key_skills": [],
        "ai_taxonomies_a": ["Technology", "Software"],
        "ai_core_responsibilities": description[:280] if description else None,
        "ai_requirements_summary": None,
        "description_text": description,
        "linkedin_org_employees": None,
        "linkedin_org_industry": _str(row.get("company_industry")),
        "linkedin_org_size": None,
        "linkedin_org_recruitment_agency_derived": is_agency,
        "linkedin_org_specialties": [],
        "linkedin_org_description": None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window-days", type=int, required=True)
    ap.add_argument("--location", default="United States")
    ap.add_argument("--country-indeed", default="USA")
    ap.add_argument("--results-per-search", type=int, default=30,
                    help="Results per site per search term (default 30; total ≈ terms × sites × this)")
    ap.add_argument("--output", required=True)
    ap.add_argument("--sites", nargs="+",
                    default=["indeed", "glassdoor", "google", "zip_recruiter"],
                    help="Sites to scrape. linkedin is opt-in (slow + rate-limited).")
    ap.add_argument("--include-linkedin", action="store_true",
                    help="Also scrape LinkedIn (caps at ~50/term, may rate-limit).")
    ap.add_argument("--terms", nargs="+", default=None,
                    help="Override default search terms.")
    ap.add_argument("--company", default=None,
                    help="Targeted single-company crawl — overrides --terms.")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    out_path = Path(os.path.expanduser(args.output))
    sites = list(args.sites)
    if args.include_linkedin and "linkedin" not in sites:
        sites.append("linkedin")

    hours_old = max(1, args.window_days * 24)
    terms = [args.company] if args.company else (args.terms or DEFAULT_SEARCH_TERMS)

    if not args.quiet:
        print(f"jobspy: window={args.window_days}d ({hours_old}h)  location={args.location!r}  sites={sites}  terms={len(terms)}", file=sys.stderr)

    all_rows = []
    for i, term in enumerate(terms, 1):
        if not args.quiet:
            print(f"  [{i}/{len(terms)}] scraping '{term}' …", file=sys.stderr)
        try:
            df = scrape_jobs(
                site_name=sites,
                search_term=term,
                google_search_term=f"{term} jobs in {args.location} since past {args.window_days} days",
                location=args.location,
                hours_old=hours_old,
                results_wanted=args.results_per_search,
                country_indeed=args.country_indeed,
                description_format="markdown",
                linkedin_fetch_description=("linkedin" in sites),
                enforce_annual_salary=True,
                job_type="fulltime",
                verbose=0,
            )
            if df is None or len(df) == 0:
                continue
            for _, row in df.iterrows():
                all_rows.append(row.to_dict())
            if not args.quiet:
                print(f"      → {len(df)} raw rows", file=sys.stderr)
        except Exception as e:
            print(f"      ! '{term}' failed: {e}", file=sys.stderr)

    # Dedup by URL + title-exclude prefilter
    seen_urls = set()
    items = []
    dropped_excluded = 0
    for r in all_rows:
        url = (r.get("job_url") or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        tl = (r.get("title") or "").lower()
        if any(x in tl for x in TITLE_EXCLUDE):
            dropped_excluded += 1
            continue
        items.append(row_to_apify_shape(r))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"items": items, "totalItemCount": len(items)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"jobspy: {len(items)} items written ({dropped_excluded} title-excluded, {len(all_rows)-len(seen_urls)} duplicates) → {out_path}", file=sys.stderr)
    # Echo path to stdout so the slash command can capture it
    print(str(out_path))


if __name__ == "__main__":
    main()
