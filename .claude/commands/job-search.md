---
description: Run the daily job-search crawl through Apify. Pass a time window (1d/3d/7d/14d/30d) or a sub-command ("show me jobs from <Company>", "I applied to <Company>", "reset job history"). Default window is 1d.
argument-hint: [1d|3d|7d|14d|30d | "show me jobs from <Company>" | "I applied to <Company>" | "reset job history"]
allowed-tools: Bash, Read, Edit, Write, mcp__Apify__call-actor, mcp__Apify__get-actor-output, mcp__Apify__search-actors, mcp__Apify__fetch-actor-details
---

You are running the job-search workflow **inline in the main turn**, not via the sub-agent.

> **Why inline?** Claude Code sub-agents don't inherit the parent's MCP server access by default, so `mcp__Apify__*` tools aren't reachable from inside the `job-search` sub-agent. The sub-agent definition at `.claude/agents/job-search.md` is the operational spec; the slash command runs it.

## Primary output: `jobs_ui/index.html`

Each scan **appends a new session** to `E:\_Resume-Curator\job_search\jobs_ui\data.js`. The user opens `jobs_ui/index.html` in their browser and toggles between sessions via the dropdown. HTML and CSS never need to be regenerated — the data file is the only thing that changes.

- HTML/UI: `E:\_Resume-Curator\job_search\jobs_ui\index.html` (do NOT modify on every run)
- Data:    `E:\_Resume-Curator\job_search\jobs_ui\data.js` (appended-to by `render_results.py`)
- Backup MD: `~/.job_search/sessions/jobs_<date>_<window>.md` (still written for audit)

## Arguments

`$ARGUMENTS` may be empty or contain a time window / sub-command.

### Parse step (do FIRST)

1. **Empty / no time token** → window = `1d`.
2. **`<N>d` or `<N>h` / `<N>w` / `<N>m`** → set `window_days` accordingly.
3. **Sub-commands** (mutually exclusive with a crawl):
   - `I applied to <Company>` → append company (lowercased trimmed) to `preferences.applied_or_tracking` in `~/.job_search/state.json`, write back atomically, confirm to user, **STOP**.
   - `reset job history` → ask the user to confirm in one short message. If confirmed, clear `seen_job_ids` and write state. **STOP**.
   - `show me jobs from <Company>` / `re-score <Company>` → run a targeted crawl: set `organizationSearch: [<Company>]` on the primary actor, keep the rest of the input but expand `limit` to 200 and drop `titleSearch` / `titleExclusionSearch`.
4. Otherwise → full crawl with the parsed window.

Echo the parsed mode + window at the start:
```
[mode: full crawl] [window: 7d] [sources: apify:fantastic-jobs]
```

## Execute the crawl (full or targeted)

### Step A — load state

Read `~/.job_search/state.json`. Bind `prefs = state.preferences`, `seen = state.seen_job_ids`, `apify_cfg = prefs.crawl_sources.apify`. Verify `apify` is in `prefs.crawl_sources.enabled` — if not, error and stop.

### Step B — compute datePostedAfter

`today = date.today()` (use `date -I` in bash if needed). `datePostedAfter = today - window_days`. Format `YYYY-MM-DD`.

### Step C — call the primary Apify actor

Call `mcp__Apify__call-actor` with:
- `actor: "fantastic-jobs/career-site-job-listing-api"`
- `input`:
  ```json
  {
    "timeRange": "6m",
    "datePostedAfter": "<computed>",
    "limit": 200,
    "descriptionType": "text",
    "includeAi": true,
    "includeLinkedIn": true,
    "removeAgency": true,
    "titleSearch": ["AI Engineer","LLM Engineer","Machine Learning Engineer","ML Engineer","Founding Engineer","Forward Deployed","Applied AI","Applied Scientist","Agentic","Research Engineer","Software Engineer AI","AI Engineer Associate","Junior AI Engineer","Associate AI Engineer","Entry Level AI"],
    "titleExclusionSearch": ["Senior","Sr","Sr.","Lead","Staff","Principal","Director","VP","Head","Manager","Chief","Sales","Marketing","Recruiter","Designer","Frontend"],
    "locationSearch": ["United States"],
    "aiEmploymentTypeFilter": ["FULL_TIME"],
    "aiExperienceLevelFilter": ["0-2","2-5"],
    "aiTaxonomiesPrimaryFilter": ["Technology","Software","Engineering","Data & Analytics"]
  }
  ```
- `callOptions: { memory: 1024, timeout: 300 }`
- `previewOutput: false`

For `show me jobs from <Company>` mode: add `organizationSearch: ["<Company>"]`, drop `titleSearch` / `titleExclusionSearch`, raise `limit` to 200.

### Step D — fetch the full dataset to disk

Call `mcp__Apify__get-actor-output` with the returned `datasetId`, requesting only the fields the scoring script needs:
```
id,date_posted,title,organization,locations_derived,countries_derived,remote_derived,url,source,ai_employment_type,ai_experience_level,ai_work_arrangement,ai_visa_sponsorship,ai_salary_minvalue,ai_salary_maxvalue,ai_salary_currency,ai_key_skills,ai_taxonomies_a,ai_core_responsibilities,ai_requirements_summary,description_text,linkedin_org_employees,linkedin_org_industry,linkedin_org_size,linkedin_org_recruitment_agency_derived,linkedin_org_specialties,linkedin_org_description
```

The MCP response will exceed context and auto-save to a tool-results path — capture that path from the error message. (Expected for 100 items.)

### Step E — score + append to data.js + archive

Run the render script. It writes:
1. A new session entry into `jobs_ui/data.js` (newest-first).
2. A backup MD at `~/.job_search/sessions/jobs_<date>_<window>.md`.
3. Atomic update of `~/.job_search/state.json` (appends shown `job_ids` + `session_log` entry).

```bash
python "C:/Users/prana/.job_search/render_results.py" \
  --dataset "<path-from-step-D>" \
  --window-days <N> \
  --today "$(date -I)"
```

The script enforces:
- Title-level drop: Senior/Sr/Lead/Staff/Principal/Manager/Director/VP/Head/Chief
- Experience drop: `ai_experience_level` in {5-10, 10+}, or JD requires 4+ yrs
- Sponsorship hard filter: drops "must be authorized to work without sponsorship" JDs (NOT down-rank)
- Defense / clearance / citizenship-gated drops
- Non-US / recruitment-agency drops
- Current employer (`alfred_`) + already-applied drops
- Dedup against `seen_job_ids`
- Dedup duplicate postings within the run (same company + normalised title)

### Step F — relay output

The script prints a short summary with the HTML path and the MD path. Relay verbatim. Also tell the user explicitly:

```
✅ Done. Open in browser: file:///E:/_Resume-Curator/job_search/jobs_ui/index.html
```

Optionally show top 10–15 inline as preview blocks (compact MD format from the script's MD output), then point them at the HTML for the rest + filters.

## Rules

- **Never fabricate.** If the actor errors, surface the error verbatim.
- **Allowlist is hard.** Don't crawl actors outside `apify_cfg.primary_actor` / `apify_cfg.secondary_actor` without updating state first.
- **Cost ceiling ~$3 per run.** Primary actor at FREE tier is $0.012/job × 200 = $2.40; within budget.
- **Do not regenerate `jobs_ui/index.html`.** The HTML is a one-time write. If a UI improvement is genuinely needed, ask the user first.
- **Append-only `data.js`.** The script overwrites only entries with the same session id (same date + window). Past sessions remain visible.

## Examples

- `/job-search` → window `1d`, full crawl
- `/job-search 7d` → window `7d`, full crawl
- `/job-search 14d, focus on agentic AI` → window `14d`, full crawl (extra emphasis is informational)
- `/job-search show me jobs from Cohere` → targeted Cohere crawl across last 7d (default)
- `/job-search I applied to Anthropic` → state mutation only, no crawl
- `/job-search reset job history` → destructive; confirm first
