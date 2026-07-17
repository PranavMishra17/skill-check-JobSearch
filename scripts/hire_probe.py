"""hire_probe.py — Tier-A (zero-signup) hire-search email/contact prober.

PROTOTYPE for scoping. Given a company (name + domain, optional GitHub org) and
optionally a few known person names, it demonstrates the free email-discovery
pipeline from HIRE_SEARCH_RESEARCH.md:

  1. GitHub commit-author email harvest for the org  (EXACT emails, free)
  2. Email permutation generation                    (guesses, weighted by size)
  3. MX record lookup  (dnspython)                    (domain deliverability)
  4. SMTP RCPT-TO probe (smtplib, best-effort)        (verify without sending)
  5. LinkedIn Google-dork URL construction           (people discovery)

Grades each candidate email: verified | mx-ok-guess | catch-all | invalid.
No paid API, no signup. GitHub token optional (raises rate limit) via $GITHUB_TOKEN.

Usage:
  python hire_probe.py --company "Reducto" --domain reducto.ai --github reducto \
      --names "Adit Abraham" "Raunak Chowdhuri" --size 30
"""
import argparse, json, os, re, smtplib, socket, sys, time
from urllib.parse import quote_plus

try:
    import dns.resolver
except ImportError:
    dns = None
try:
    import requests
except ImportError:
    requests = None

UA = {"User-Agent": "hire-probe/0.1 (personal job-search)"}


# ---------- name → email permutations ----------

def name_parts(full):
    toks = re.sub(r"[^a-zA-Z\- ]", "", full or "").lower().split()
    if not toks:
        return None, None
    first = toks[0]
    last = toks[-1] if len(toks) > 1 else ""
    return first, last


def permutations_for(full, domain, size_tier):
    """Return candidate addresses ordered by prior likelihood for the headcount tier.
    size_tier: approx employee count (int). Weights per research (51-200 vs 1000+)."""
    first, last = name_parts(full)
    if not first:
        return []
    fi = first[0]
    li = last[0] if last else ""
    d = domain.lower().lstrip("@")

    # pattern -> address
    pats = {
        "first.last": f"{first}.{last}@{d}" if last else None,
        "flast":      f"{fi}{last}@{d}" if last else None,
        "first":      f"{first}@{d}",
        "firstlast":  f"{first}{last}@{d}" if last else None,
        "first_last": f"{first}_{last}@{d}" if last else None,
        "f.last":     f"{fi}.{last}@{d}" if last else None,
        "firstl":     f"{first}{li}@{d}" if last else None,
        "last.first": f"{last}.{first}@{d}" if last else None,
        "lastf":      f"{last}{fi}@{d}" if last else None,
        "fl":         f"{fi}{li}@{d}" if last else None,
    }
    # order by prevalence for the tier (research: mid-market vs enterprise)
    if size_tier >= 1000:
        order = ["first.last", "flast", "f.last", "firstlast", "first", "firstl", "first_last", "last.first", "lastf", "fl"]
    else:  # startups / mid-market: flast leads, then first.last, then first
        order = ["flast", "first.last", "first", "f.last", "firstlast", "firstl", "first_last", "last.first", "lastf", "fl"]

    out = []
    seen = set()
    for pat in order:
        a = pats.get(pat)
        if a and a not in seen:
            seen.add(a)
            out.append({"pattern": pat, "email": a})
    return out


# ---------- MX + SMTP verification ----------

def mx_hosts(domain):
    if dns is None:
        return []
    try:
        ans = dns.resolver.resolve(domain, "MX")
        return [str(r.exchange).rstrip(".") for r in sorted(ans, key=lambda r: r.preference)]
    except Exception:
        return []


def smtp_probe(email, mx, timeout=10, sender="verify@example.com"):
    """RCPT TO handshake without sending DATA. Returns (code, msg) or (None, reason)."""
    try:
        with smtplib.SMTP(mx, 25, timeout=timeout) as s:
            s.ehlo_or_helo_if_needed()
            s.mail(sender)
            code, msg = s.rcpt(email)
            return code, (msg.decode() if isinstance(msg, bytes) else str(msg))
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def catch_all(domain, mx):
    """A random unlikely address that still gets 250 => catch-all domain."""
    bogus = f"zz-no-such-user-9713xk@{domain}"
    code, _ = smtp_probe(bogus, mx)
    return code == 250


def verify_email(email, mx, is_catch_all):
    if not mx:
        return "invalid", "no-MX"
    if is_catch_all:
        return "catch-all", "domain accepts any address"
    code, msg = smtp_probe(email, mx)
    if code == 250:
        return "verified", msg[:80]
    if code is None:
        return "mx-ok-guess", msg[:80]  # probe blocked/errored; MX exists
    return "invalid", f"{code} {msg[:60]}"


# ---------- GitHub commit-author email harvest ----------

def github_org_emails(org, max_repos=8, max_commits=30):
    """Public commit-author emails for an org's repos. Skips noreply. Free."""
    if requests is None:
        return []
    tok = os.environ.get("GITHUB_TOKEN")
    h = dict(UA)
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    found = {}
    try:
        r = requests.get(f"https://api.github.com/orgs/{org}/repos",
                         params={"sort": "pushed", "per_page": max_repos}, headers=h, timeout=15)
        if r.status_code != 200:
            # maybe it's a user, not an org
            r = requests.get(f"https://api.github.com/users/{org}/repos",
                             params={"sort": "pushed", "per_page": max_repos}, headers=h, timeout=15)
        repos = r.json() if r.status_code == 200 else []
    except Exception:
        return []
    if not isinstance(repos, list):
        return []
    for repo in repos[:max_repos]:
        name = repo.get("name")
        if not name:
            continue
        try:
            cr = requests.get(f"https://api.github.com/repos/{org}/{name}/commits",
                              params={"per_page": max_commits}, headers=h, timeout=15)
            commits = cr.json() if cr.status_code == 200 else []
        except Exception:
            continue
        if not isinstance(commits, list):
            continue
        for c in commits:
            commit = (c or {}).get("commit", {})
            author = commit.get("author", {}) or {}
            email = (author.get("email") or "").lower()
            nm = author.get("name") or ""
            if not email or "noreply" in email or email.endswith("users.noreply.github.com"):
                continue
            login = ((c.get("author") or {}) or {}).get("login") or ""
            if email not in found:
                found[email] = {"email": email, "name": nm, "login": login, "repo": name}
        time.sleep(0.3)  # be polite to the API
    return list(found.values())


# ---------- LinkedIn dork ----------

def linkedin_dorks(name, company, location=""):
    q1 = f'site:linkedin.com/in "{name}" "{company}"'
    q2 = f'site:linkedin.com/in "{company}" (recruiter OR "talent" OR "engineering manager")'
    if location:
        q2 += f' "{location}"'
    return {
        "person_query": q1,
        "person_url": f"https://www.google.com/search?q={quote_plus(q1)}",
        "team_query": q2,
        "team_url": f"https://www.google.com/search?q={quote_plus(q2)}",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--company", required=True)
    ap.add_argument("--domain", required=True, help="email domain, e.g. reducto.ai")
    ap.add_argument("--github", default=None, help="github org/user login")
    ap.add_argument("--names", nargs="*", default=[], help="known person names to guess emails for")
    ap.add_argument("--location", default="")
    ap.add_argument("--size", type=int, default=50, help="approx employee count (weights guesses)")
    ap.add_argument("--no-smtp", action="store_true", help="skip SMTP probe (MX only)")
    args = ap.parse_args()

    report = {"company": args.company, "domain": args.domain, "steps": {}}

    # 1) MX
    mx = mx_hosts(args.domain)
    report["steps"]["mx"] = {"hosts": mx[:3], "deliverable": bool(mx)}
    is_ca = False
    if mx and not args.no_smtp:
        is_ca = catch_all(args.domain, mx[0])
    report["steps"]["mx"]["catch_all"] = is_ca

    # 2) GitHub commit emails (exact)
    gh = github_org_emails(args.github) if args.github else []
    # keep only same-domain or notable
    gh_domain = [g for g in gh if g["email"].endswith("@" + args.domain.lower())]
    report["steps"]["github"] = {
        "org": args.github,
        "total_emails": len(gh),
        "same_domain_emails": gh_domain,
        "sample_other": [g["email"] for g in gh[:10]],
    }

    # 3) permutations + verify for known names
    people = []
    for nm in args.names:
        cands = permutations_for(nm, args.domain, args.size)
        graded = []
        for c in cands[:4]:  # top-4 patterns only, to limit SMTP calls
            if args.no_smtp or not mx:
                grade, detail = ("mx-ok-guess" if mx else "invalid"), "smtp-skipped"
            else:
                grade, detail = verify_email(c["email"], mx[0], is_ca)
            graded.append({**c, "grade": grade, "detail": detail})
            if grade == "verified":
                break
        best = next((g for g in graded if g["grade"] == "verified"),
                    graded[0] if graded else None)
        people.append({"name": nm, "best": best, "candidates": graded,
                       "linkedin": linkedin_dorks(nm, args.company, args.location)})
    report["steps"]["people"] = people

    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
