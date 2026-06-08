---
description: Run the daily job-search crawl. Primary crawler is JobSpy (free, local, scrapes Indeed/Glassdoor/Google/ZipRecruiter/LinkedIn). Apify retained as fallback via "--apify". Pass a time window (1d/3d/7d/14d/30d) or a sub-command ("show me jobs from <Company>", "I applied to <Company>", "reset job history"). Default window is 1d.
argument-hint: [1d|3d|7d|14d|30d | "show me jobs from <Company>" | "I applied to <Company>" | "reset job history" | --apify]
allowed-tools: Bash, Read, Edit, Write, mcp__Apify__call-actor, mcp__Apify__get-actor-output, mcp__Apify__search-actors, mcp__Apify__fetch-actor-details
---

You run the job-search workflow **inline in the main turn**, not via the sub-agent.

> **Why inline?** Claude Code sub-agents don't inherit the parent's MCP server access by default, so `mcp__Apify__*` tools aren't reachable from inside the `job-search` sub-agent. The sub-agent definition at `.claude/agents/job-search.md` is the operational spec; the slash command runs it.

## Primary crawler: multi-source `crawl_all.py` (free, local)

The default crawler is **`C:/Users/prana/.job_search/crawl_all.py`** — a multi-source orchestrator that fuses four free sources into one Apify-shape JSON:

1. **[JobSpy](https://github.com/speedyapply/JobSpy)** — Indeed, Google Jobs, Glassdoor (LinkedIn opt-in). 17 search terms covering AI/ML/agentic/founding/forward-deployed/MLOps/research/etc.
2. **GitHub `SimplifyJobs/New-Grad-Positions`** — `listings.json` parsed directly, filtered to AI/ML titles.
3. **GitHub `speedyapply/2026-AI-College-Jobs`** — daily-updated AI/ML new-grad markdown table.
4. **[Arbeitnow](https://www.arbeitnow.com/api/job-board-api)** — free public API, filtered to AI/ML titles.

All outputs normalised to the same Apify schema and cross-source URL-deduped. `render_results.py` consumes the unified JSON unchanged.

The single-source crawler `crawl_jobspy.py` is retained for `--single-source` runs. Apify (`fantastic-jobs/career-site-job-listing-api`) stays as a `--apify` fallback for ATS-direct coverage (Workday/Greenhouse/Ashby/Lever) when needed.

## Output

Each scan **appends a new session** to `E:\_Resume-Curator\job_search\jobs_ui\data.js`. The user opens `jobs_ui/index.html` in their browser and toggles between sessions via the dropdown. HTML and CSS never need to be regenerated — the data file is the only thing that changes.

- HTML/UI: `E:\_Resume-Curator\job_search\jobs_ui\index.html` (do NOT modify on every run)
- Data:    `E:\_Resume-Curator\job_search\jobs_ui\data.js` (appended-to by `render_results.py`)
- Backup MD: `~/.job_search/sessions/jobs_<date>_<window>.md`
- Raw JobSpy JSON: `~/.job_search/raw_jobs/<date>_<window>.json`

## Arguments

`$ARGUMENTS` may be empty or contain a time window / sub-command / `--apify` flag.

### Parse step (do FIRST)

1. **Empty / no time token** → window = `1d`.
2. **`<N>d` or `<N>h` / `<N>w` / `<N>m`** → set `window_days` accordingly.
3. **`--apify`** anywhere in args → use Apify fallback path (Step C-alt below) instead of JobSpy.
4. **Sub-commands** (mutually exclusive with a crawl):
   - `I applied to <Company>` → append company (lowercased trimmed) to `preferences.applied_or_tracking` in `~/.job_search/state.json`, write back atomically, confirm to user, **STOP**.
   - `reset job history` → ask the user to confirm in one short message. If confirmed, clear `seen_job_ids` and write state. **STOP**.
   - `show me jobs from <Company>` / `re-score <Company>` → JobSpy with `--company "<Company>"` (treats the company name as the search term, raises `results_per_search` to 50, drops the title-include filter).
5. Otherwise → full crawl with the parsed window.

Echo the parsed mode + window at the start:
```
[mode: full crawl] [window: 7d] [source: jobspy (indeed,glassdoor,google,zip_recruiter)]
```

## Execute (JobSpy — default path)

### Step A — load state

Read `~/.job_search/state.json`. Bind `prefs = state.preferences`, `seen = state.seen_job_ids`. Verify `crawl_jobspy.py` exists at `C:/Users/prana/.job_search/crawl_jobspy.py`.

### Step B — run the multi-source crawler

```bash
python "C:/Users/prana/.job_search/crawl_all.py" \
  --window-days <N> \
  --location "United States" \
  --results-per-search 30 \
  --output "C:/Users/prana/.job_search/raw_jobs/$(date -I)_<N>d.json"
```

Optional flags:
- `--include-linkedin` — adds LinkedIn to JobSpy (slow, often rate-limits; opt-in only).
- `--company "<Name>"` — single-company crawl (for `show me jobs from <Company>` mode). Disables GitHub + Arbeitnow sources (those don't support company search).
- `--terms "Term1" "Term2" ...` — override the default 17-term search list (JobSpy only).
- `--no-jobspy` / `--no-github` / `--no-arbeitnow` — selectively disable individual sources.

The orchestrator handles:
- All four sources, additive (failure in one doesn't block the rest)
- Title pre-filter (drops obvious Senior/Staff/Principal/Manager/VP/Head/Chief titles, plus pure-frontend/sales/marketing)
- AI-scope filter on generic feeds (Arbeitnow, Simplify) — keeps only AI/ML/engineering titles
- Window filter (drops anything older than `--window-days`)
- Cross-source URL dedup + (company, normalised title) dedup
- Normalisation to the same Apify-shape JSON that `render_results.py` expects

If JobSpy yields little (e.g. all sites 429), the GitHub + Arbeitnow sources still provide coverage. Use `--single-source` to fall back to the older `crawl_jobspy.py` script if needed.

### Step C — score + append to data.js + archive

The crawl script echoes its output path to stdout. Pass that path to the renderer:

```bash
python "C:/Users/prana/.job_search/render_results.py" \
  --dataset "<path-from-step-B>" \
  --window-days <N> \
  --today "$(date -I)"
```

The renderer enforces:
- Title-level drop: Senior/Sr/Lead/Staff/Principal/Manager/Director/VP/Head/Chief
- Experience drop: `ai_experience_level` in {5-10, 10+}, or JD requires 4+ yrs
- Sponsorship hard filter: drops "must be authorized to work without sponsorship" JDs
- Defense / clearance / citizenship-gated drops
- Non-US / recruitment-agency drops
- Current employer (`alfred_`) + already-applied drops
- Dedup against `seen_job_ids`
- Dedup duplicate postings within the run (same company + normalised title)

It writes:
1. A new session entry into `jobs_ui/data.js` (newest-first).
2. A backup MD at `~/.job_search/sessions/jobs_<date>_<window>.md`.
3. Atomic update of `~/.job_search/state.json` (appends shown `job_ids` + `session_log` entry).

## Execute (Apify — fallback path, only when `--apify` is passed)

Use the Apify route if JobSpy is unavailable or coverage is insufficient. The Apify actor covers ATS direct sites (Workday, Greenhouse, Ashby, Lever) that JobSpy doesn't.

### Step C-alt — call the Apify actor

`mcp__Apify__call-actor` with `actor: "fantastic-jobs/career-site-job-listing-api"`:
```json
{
  "timeRange": "6m",
  "datePostedAfter": "<today minus N days>",
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
`callOptions: { memory: 1024, timeout: 300 }`, `previewOutput: false`.

For `show me jobs from <Company>` mode under `--apify`: add `organizationSearch: ["<Company>"]`, drop `titleSearch` / `titleExclusionSearch`, raise `limit` to 200.

### Step D-alt — fetch full dataset

`mcp__Apify__get-actor-output` with the returned `datasetId`, requesting the same fields list as before. Save to the tool-results path; pass that path to `render_results.py` exactly like the JobSpy path.

### Pre-flight for Apify

If the actor returns `"Maximum charged results must be greater than zero"`, the per-run charge cap in the Apify console is set to 0. The user must raise it in console.apify.com → actor settings → *Maximum charged results per run* before retrying.

## Step F — relay output

The renderer prints a short summary with the HTML path and the MD path. Relay verbatim. Then explicitly:

```
✅ Done. Open in browser: file:///E:/_Resume-Curator/job_search/jobs_ui/index.html
Live: https://pranavmishra17.github.io/skill-check-JobSearch/
```

Optionally show top 10–15 inline as preview blocks, then point at the HTML for the rest.

## Rules

- **Never fabricate.** If JobSpy or the actor errors, surface the error verbatim.
- **Default to JobSpy.** Only use Apify when the user passes `--apify` or JobSpy fails / coverage is too thin.
- **Cost.** JobSpy is free (no API). Apify path is ~$2.40 per 200-job crawl on the FREE tier — confirm with user before running large Apify crawls.
- **Do not regenerate `jobs_ui/index.html`.** Static asset.
- **Append-only `data.js`.** The renderer overwrites only entries with the same session id (same date + window). Past sessions remain visible.

## Examples

- `/job-search` → JobSpy, 1d window
- `/job-search 7d` → JobSpy, 7d window
- `/job-search 14d, focus on agentic AI` → JobSpy, 14d (the extra phrase is informational)
- `/job-search show me jobs from Cohere` → JobSpy with `--company "Cohere"`
- `/job-search 7d --apify` → Apify fallback path, 7d window (e.g. if you specifically want ATS-direct coverage)
- `/job-search I applied to Anthropic` → state mutation only, no crawl
- `/job-search reset job history` → destructive; confirm first
