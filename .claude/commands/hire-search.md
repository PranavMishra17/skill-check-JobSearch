---
description: Find the humans who hire for the jobs in your latest /job-search crawl — recruiters, people/HR leads, hiring managers, founders (engineers only as a last resort) — with a real, SMTP-verified email for each. Zero Apify. Walks the top-scoring jobs of the most-recent job-search session, uses each job's metadata (company/role/team/location) to hunt the hiring team via the Brave Search API, then recovers emails via name+domain permutation + single-connection SMTP verification (+ GitHub commit emails for engineers). Pass an optional target count and/or a scope label.
argument-hint: [<N> (target job count, default 50) | "founding" | "remote" | dry-run]
allowed-tools: Bash, Read, Edit, Write
---

You run **hire-search** inline in the main turn. It is now **fully off Apify** and reuses the `/job-search` crawl. See `docs/HIRE_SEARCH_RESEARCH.md` for scoping research and `scripts/hire_crawl.py` for the pipeline.

## What it does

For the **latest** `/job-search` session (top-scoring jobs first), for each job it uses **only the job's metadata** (company, title, team, location — never the job URL) to find who hires there, in priority order:

1. recruiter / talent acquisition
2. head of people / HR leadership
3. hiring manager / engineering lead
4. founder / CEO / CTO (startups)
5. engineers on/near that team — **last resort only** (GitHub commit authors)

For every person it recovers a **real email**: GitHub commit-author email (exact) when available, else a name+domain permutation graded by a single-connection SMTP RCPT-TO probe (`verified | mx-ok-guess | catch-all | invalid`). It collects a **list of `--target` jobs (default 50) that each yielded ≥1 contact**, backfilling down the ranked list if the top-N don't reach the target.

Output: prepends a session to `jobs_ui/hires.js` (dashboard reads it), writes an MD backup, updates `~/.job_search/state.json`.

## Preflight (do FIRST)

1. `jobs_ui/data.js` has at least one session. If not: tell the user to run `/job-search` first and STOP.
2. Brave key present: env `BRAVE_API_KEY` **or** file `~/.job_search/brave_key.txt`. If neither and provider is not `searxng`:
   - Tell the user: create a free key at https://api.search.brave.com/app/keys ("Data for Search" free tier — 2,000 queries/mo, no card), then `setx BRAVE_API_KEY <key>` or save it to `C:\Users\prana\.job_search\brave_key.txt`. STOP until provided.
3. `dnspython` + `requests` importable (installed). Outbound port 25 is open here, so SMTP verification works locally.

## Arguments

Parse `$ARGUMENTS` (any order, all optional):
- **Integer `<N>`** → `--target N` (jobs-with-contacts to collect; default 50).
- **`dry-run`** → add `--dry-run`.
- **`searxng`** → `--provider searxng` (keyless fallback; flaky/rate-limited — prefer Brave).
- **Label token** (`founding`, `remote`, `india`, any word) → `--label <token>`. Default `us-ai`.

Echo at start:
```
[mode: hire-search] [label: us-ai] [target: 50] [provider: brave] [source: latest /job-search session]
```

## Execute

```bash
python "scripts/hire_crawl.py" --today "$(date -I)" --label "<label>" --provider brave --target <N>
```

Flags: `--contacts-per-job 2`, `--size-tier 120`, `--no-verify` (MX-only, faster), `--max-jobs 120`, `--session-id <id>`, `--dry-run`.

Relay the script's final summary verbatim (`contacts=… with-email=… verified=…`).

## Cost / limits

- **$0.** Brave free tier = 2,000 queries/month, 1 query/sec. A 50-job run ≈ 50–150 queries ≈ 2–3 min ≈ ~13 full runs/month.
- SMTP verify adds ~1–3 s per person (single connection, early-exit).

## Rules

- **Never fabricate.** A person is recorded only if a search result (LinkedIn or people-aggregator) or GitHub commit names them. Emails are `verified` only on a real SMTP `250`; guesses are graded `mx-ok-guess`, never shown as verified.
- **Never scrape search engines directly.** Static + headless-browser scraping of Google/Bing/DDG is anti-bot-blocked (verified). Brave API or SearXNG JSON only.
- **Do not visit the job posting URL** to find people — metadata only.
- **Engineers are a last resort** — only when tiers 1–4 find nobody.
- **Do not regenerate `jobs_ui/hires.html`.** Static asset (a one-time edit to render the email field is fine).
- **Append-only `hires.js`.** Same session id overwrites in place.

## Examples

- `/hire-search` → top 50 jobs from latest session, Brave, label `us-ai`
- `/hire-search 20` → target 20 jobs-with-contacts
- `/hire-search dry-run 10` → print 10 jobs' contacts, write nothing
- `/hire-search searxng 15` → keyless fallback, target 15
