# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this directory is

A standalone daily job-search agent for Pranav Mishra. Sibling to the resume curator (see `../CLAUDE.md`), but with independent state and an independent workflow. Not a code repo — there is no build, no tests, no lint. Everything here is read-only profile material plus an agent definition that crawls job boards, scores results, and dedupes against past sessions.

## Layout

```
job_search/
├── CLAUDE.md                  ← this file
├── profile/                   ← read-only candidate inputs
│   ├── RESUME Pranav_Mishra.pdf
│   ├── PRANAV_PORTFOLIO.pdf
│   ├── ALFRED_ROLE.md         ← current role @ alfred_ (founding LLM Eng)
│   ├── SNAKEAI.md             ← project deep-dive
│   └── WHEELPRICE.md          ← prior role deep-dive
├── jobs_ui/                   ← browser-facing job board (primary output)
│   ├── index.html             ← static UI shell — NEVER regenerated
│   └── data.js                ← `window.JOB_SESSIONS = [...]` — appended per scan
└── .claude/
    ├── agents/
    │   └── job-search.md      ← sub-agent spec (documentation)
    └── commands/
        └── job-search.md      ← `/job-search` slash command — runs the crawl inline
```

The user opens `jobs_ui/index.html` in a browser to view results. Each scan appends a new session to `data.js`; the HTML reads it and lets the user toggle between sessions via a dropdown. **Never regenerate index.html — it's a fixed asset.**

State lives **outside** this directory at `~/.job_search/` (POSIX) / `C:\Users\prana\.job_search\` (Windows):

| Path | Purpose |
|---|---|
| `~/.job_search/state.json` | Source of truth: `candidate_profile`, `preferences`, `seen_job_ids`, `session_log` |
| `~/.job_search/sessions/YYYY-MM-DD.json` | Per-day archive of full crawl results |

The canonical resume reference for content/metrics lives at `../PRANAV_MASTER_REFERENCE.md` — defer to it for any factual claim about projects, dates, or numbers.

## How to invoke the job-search agent

**Preferred: the `/job-search` slash command** (defined in `.claude/commands/job-search.md`). It thin-wraps the sub-agent and passes arguments through verbatim.

| Slash invocation | Behaviour |
|---|---|
| `/job-search` | 1d default — past 24 hours |
| `/job-search 3d` | past 3 days |
| `/job-search 7d` | past week |
| `/job-search 14d` | past two weeks |
| `/job-search 30d` | past month |
| `/job-search 7d, focus on agentic AI` | 7-day window with extra emphasis |
| `/job-search show me jobs from Cohere` | targeted single-company crawl |
| `/job-search I applied to Anthropic` | mutates `preferences.applied_or_tracking`, no crawl |
| `/job-search reset job history` | clears `seen_job_ids` (destructive — confirms first) |

**How the slash command actually runs:**

The `/job-search` slash command runs the workflow **inline in the main turn** — it does not delegate to the sub-agent. This is intentional: Claude Code sub-agents don't inherit the parent's MCP server access by default, so `mcp__Apify__*` tools are unreachable from inside a sub-agent thread.

- `.claude/commands/job-search.md` → the runtime (slash command body — argument parsing, Apify actor call, scoring script invocation)
- `.claude/agents/job-search.md` → the operational **spec** (PHASE 0→6 contract, scoring rubric). Reference for documentation; not the runtime path.
- `C:\Users\prana\.job_search\score_and_archive.py` → the scoring + archival script. Reads the saved Apify dataset, applies pre-filters, scores, writes `~/.job_search/sessions/<date>.json` and atomically updates `state.json`.

The sub-agent definition still exists for documentation, and direct `Agent({subagent_type: "job-search", ...})` invocations are technically valid — but they'll fail at the Apify call because the sub-agent can't reach the MCP server. Use the slash command.

## Hard constraints (do not break)

1. **Crawl source is Apify only (via MCP).** All crawls go through Apify-hosted actors. Current actors: `fantastic-jobs/career-site-job-listing-api` (primary — ATS direct: Workday/Greenhouse/Ashby/Lever/iCIMS/Rippling) and `valig/linkedin-jobs-scraper` (secondary — LinkedIn supplement). Indeed and Dice scraping (via any Apify actor or otherwise) are explicitly blocked. Source of truth: `preferences.crawl_sources` in state file.
2. **Never fabricate listings.** If a crawl fails, log and skip — do not invent. Partial-data listings get a `[partial data]` flag.
3. **`seen_job_ids` is the dedup source of truth.** Never reset unless the user explicitly says "reset job history."
4. **Work-authorization filter.** Drop roles that require US citizenship or active clearance — user is on F1-OPT STEM through July 2028.
5. **Dealbreaker filters** (from `preferences.dealbreakers`): no pure-frontend roles, no contract/1099, no clearance-required.
6. **Defense / military are blocked.** Citizenship-gated; not viable.

## Workflow contract (PHASE 0 → 6)

The full spec lives inside the sub-agent definition. Skeleton:

- **PHASE 0** — bootstrap check: if `~/.job_search/state.json` missing, run setup (already done; this should not re-fire).
- **PHASE 3** — crawl apify only, parse listings, compute stable `job_id = sha256(company+title+url)[:16]`, filter against `seen_job_ids` and `preferences`.
- **PHASE 4** — score 0–100 across skill match (30), domain alignment (25), seniority fit (15), company signal (15), location (10), recency (5).
- **PHASE 5** — print top 20 (or all if fewer) in plain-text job blocks; print session summary.
- **PHASE 6** — append shown `job_id`s to `seen_job_ids`, append session entry to `session_log`, write `state.json`, optionally archive to `sessions/<date>.json`.

## Output naming

Per-day archives only: `~/.job_search/sessions/YYYY-MM-DD.json`. The state file itself is rewritten in place; never versioned.

## What NOT to do

- Do not edit files under `profile/` casually — those are inputs. Update `ALFRED_ROLE.md` only when the role changes (title, scope, user-count milestones).
- Do not modify `~/.job_search/state.json` by hand for routine flow updates — the agent owns it. Hand-edit is fine for one-off fixes (e.g. correcting `applied_or_tracking`).
- Do not crawl beyond the allowlist. If you think another source is needed, ask the user first and update the state file before crawling.
- Do not write a new resume here — the resume curator lives at `../`. This subdirectory is search-only.
