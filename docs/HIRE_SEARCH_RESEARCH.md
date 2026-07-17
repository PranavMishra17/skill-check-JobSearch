# Hire-search rebuild — research synthesis (2026-07-16)

Source: deep-research workflow (105 agents, 5.5M tokens, 75 claims adversarially verified — 60 survived, 15 refuted). This doc is the scoping basis for moving `/hire-search` off Apify to a free, local, profile-flexible pipeline whose **primary deliverable is real work emails + LinkedIn URLs of hiring-team people**.

---

## TL;DR — the honest reality

Finding **verified work emails for free, at volume, is the hard part** and has real failure modes. No free API reliably returns verified work emails in bulk. The workable design is a **layered funnel** that combines: (a) companies/roles we already crawl, (b) people-discovery via Google dorks + GitHub, (c) email via a small free-API budget + pattern-inference + verification. Expect a **30–55% email hit-rate** (independent Dropcontact benchmark across 15 tools / 20k contacts), not 90%.

---

## Layer 1 — WHO is hiring (companies + roles) — SOLVED, reuse existing

- 6 ATS platforms expose **public, no-auth** job APIs: **Ashby, Greenhouse, Lever, Workable, Recruitee, Personio**. We already probe 5 of these in the job-search crawler.
- **Refuted-important:** *None* of these public ATS APIs expose recruiter or hiring-manager contact info. They return job-posting fields only. → ATS gives us the **company list**, not people.
- Lever supports server-side filters (team/dept/location); the others return the full board. Personio is XML (`{company}.jobs.personio.de/xml`).

## Layer 2 — WHO are the people (names + titles)

- **Google dork (free to construct):** `site:linkedin.com/in intitle:"{TITLE}" intext:"{LOCATION}"` or `site:linkedin.com/in "recruiter" "{company}"`. Works, but **direct free Google scraping is anti-bot-throttled**; top-result accuracy ~81%; ~1.5 hr per 1000 names.
- **Google Custom Search JSON API:** 100 free queries/day, JSON out — BUT requires an API key + a Programmable Search Engine (cx id), and it is **closed to new customers and scheduled for shutdown 2027-01-01**. Do not hard-depend on it.
- **GitHub** (best for engineers/founders, not recruiters): commit-author emails from a company's public org map real engineers → real emails, **exactly, no guessing**. Tools: `git-emails`, `gitSome` (both low-adoption POC scripts — better to call the GitHub API directly). Unauthenticated works at low rate; a personal token raises limits.
- Company `/team` `/about` pages for founders/leads.

## Layer 3 — EMAILS (the core deliverable)

**Pattern inference + permutation (free, unlimited, but produces GUESSES):**
- Address format shifts by company size — weight guesses by headcount:
  - 51–200 emp: `flast@` 42%, `first.last@` 30%, `first@` 17%
  - 1000+ emp: `first.last@` 48–56%, `flast@` 22–35%, `first@` 3–7%
- Roll our own generator (~35 patterns incl. `first@`, `first.last@`, `f.last@`, `flast@`, `first_last@`, role-based `founder@/careers@`). The `email-permutations` PyPI pkg exists but is stale (2019) — don't depend on it.

**Verification without sending mail (free libs, but partially broken locally):**
- MX lookup via **dnspython** — always works, cheap. Confirms the domain can receive mail.
- SMTP `RCPT TO` handshake via **smtplib** — the "verify without sending" trick. **Major failure mode: consumer/home ISPs block outbound port 25**, so RCPT-TO verification usually FAILS from a laptop. Needs a cloud host. Even then: Gmail/Apple/Microsoft block datacenter IPs, and **15–30% of B2B domains are catch-all** (accept any address → false positives). ~3–5 s/domain.
- **Design consequence:** treat SMTP result as *best-effort*. Grade each email `verified | mx-ok-guess | catch-all | invalid`. Never present a guess as verified.

**Free email-finder APIs (small budgets; several vendor myths REFUTED):**
- **Hunter.io** — free tier is a *single unified pool of 50 credits/mo* (migrated 2025-07-16), API on free tier, search = 1 credit, verify = 0.5 credit. ⇒ ~50 finds OR 100 verifies/mo. *Refuted:* the "25 searches + 50 credits" figure some blogs cite is garbled. **Highest-leverage free move: Hunter domain-search returns the company's email PATTERN**, which lets us construct the rest for free.
- **Apollo.io** — API on all plans incl. free; ~50–100 email lookups/mo but only ~10 export credits/mo (throttles bulk pull).
- **Snov.io** — free plan has API (60 req/min) but **blocks exports on free trial** → found emails can't be pulled out. Weak.
- **Prospeo** — *Refuted:* API is **NOT** on the free tier (multiple independent sources). Free credits (75 email + 100 extension) are extension-only. Don't rely on it programmatically.
- **RocketReach** — 5 lookups/mo, API paid-only.
- Vendor accuracy claims are self-reported and inflated; independent benchmark verified-match rates: Anymail 77.5%, Hunter 37.6%, Snov 20.1%.
- Verified lists bounce <2% vs 15–30% unverified — the reason to always chain a verify step.

## Layer 4 — LinkedIn profile URL for a named person

- Same Google dork, per person; ~81% top-result accuracy, best-effort.
- **Legal:** scraping public LinkedIn is *not* a CFAA crime (hiQ v. LinkedIn, 9th Cir.), BUT hiQ still lost overall — $500k judgment on breach-of-contract + trespass-to-chattels. LinkedIn ToS prohibits automation and can ban accounts. → Use LinkedIn lightly, prefer the search-engine index over hitting LinkedIn directly, never bulk-scrape logged-in.

## Layer 5 — Legal / ethics guardrails (personal outreach, not spam)

- **CAN-SPAM (US):** cold B2B email legal w/o prior consent IF truthful from/subject, a valid physical postal address (PO box ok), and a working opt-out honored ≤10 business days. Penalty $517–$51,744 **per email**.
- **GDPR (EU):** cold B2B ok under "legitimate interest" (Art 6(1)(f)) 3-part test; honor access/erasure. Fines up to €20M or 4% turnover. B2C fails the test.
- **CASL (Canada):** stricter — needs consent; initiate non-referrals by a non-email channel. Up to CAD$10M.
- Guardrail for this tool: it **surfaces + tracks** contacts. It does not mass-send. Any outreach stays manual and low-volume, which keeps all three regimes satisfied.

---

## Recommended pipeline (ranked, buildable, free)

```
profile (target roles/locations)
      │
      ▼
[L1] companies+roles  ← reuse job-search ATS crawl (already built)
      │
      ▼
[L2] people           ← per company:
      ├── GitHub org commit-authors  (engineers/founders — EXACT emails, free)
      ├── Google dork site:linkedin.com/in  (recruiters/leads — names + LI URL)
      └── /team /about page scrape   (founders)
      │
      ▼
[L3] emails
      ├── Hunter free domain-search → company email PATTERN  (1 credit/company)
      ├── permutation generator (weighted by headcount) fills the rest — FREE
      ├── GitHub commit email = ground truth where available — FREE
      └── verify: MX (always) + SMTP RCPT-TO (best-effort, cloud only) + grade
      │
      ▼
[L4] LinkedIn URL     ← Google dork per person (best-effort, ~81%)
      │
      ▼
score + append to hires.js  (dashboard already exists)
```

**Two build tiers:**
- **Tier A — zero-signup (works today):** GitHub commit emails + permutation + MX-verify + Google-dork LinkedIn. Strong for engineers/founders at startups; weak for pure recruiters (no GitHub footprint).
- **Tier B — one free key (Hunter.io, 50/mo, no credit card):** adds the company email *pattern* → roughly triples recruiter/non-eng email hit-rate. Single highest-leverage upgrade.

## Test-scan findings (2026-07-16, prototype `scripts/hire_probe.py`)

- **Email pipeline VERIFIED working, zero-signup.** On Hugging Face: GitHub harvest returned 8 confirmed `@huggingface.co` employee emails; SMTP RCPT-TO verify returned ground-truth `250 OK` vs `550 does-not-exist` and identified the correct per-person pattern (`clement.delangue@` and `julien@` both verified real; wrong guesses correctly rejected).
- **Port 25 is OPEN on this machine** — SMTP verification works locally here, contrary to the usual home-ISP block. This removes the need for a cloud runner or Hunter's verifier.
- **Small-startup limitation confirmed:** Reducto yielded only 2 public commit emails, none `@reducto.ai`. Thin GitHub footprint = weak email recovery for tiny/non-eng-public companies.
- **Static search-engine scraping is BLOCKED (decided: use the browser).** `requests` against DuckDuckGo HTML → 202 challenge page; Bing → 200 but JS-gated, 0 parseable results; Google → CAPTCHA. Reliable free auto-scrape of LinkedIn dorks therefore requires a **real browser** (claude-in-chrome MCP, same as the apply flow), not a static HTTP fetch. People-discovery step will drive Chromium.

## Honest failure modes (tell the user upfront)
1. Free email hit-rate ~30–55%; recruiters harder than engineers.
2. SMTP RCPT-TO verify is broken from a home connection (port 25 blocked) — needs a cheap cloud runner or Hunter's verifier.
3. LinkedIn scraping is ToS-violating + anti-bot-flaky — keep it light and index-based.
4. Google Custom Search API sunsets 2027-01-01 — build on dorks-via-index, not that API.
5. Catch-all domains (15–30%) make some emails unverifiable in principle.
