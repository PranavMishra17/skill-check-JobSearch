---
description: Find people actively hiring for AI roles aligned with Pranav's profile. Combines LinkedIn hiring posts + AI/ML recruiters. Pass an age window (e.g. "5d") and/or a scope label (e.g. "founding", "india", "remote") in any order.
argument-hint: [<Nd> | "india" | "founding" | "remote" | <custom> — any order, max 2 tokens]
allowed-tools: Bash, Read, Edit, Write, mcp__Apify__call-actor, mcp__Apify__get-actor-output
---

You run the **hire-search** workflow inline in the main turn (sub-agents lack the parent's MCP access).

## Output

Each run appends a session to `E:\_Resume-Curator\job_search\jobs_ui\hires.js`. The user opens `jobs_ui/hires.html` and toggles between sessions.

## Arguments

`$ARGUMENTS` may be empty or contain up to two tokens, in any order:

### Parse step (do FIRST)

Split `$ARGUMENTS` on whitespace. For each token:

1. **Window token** — matches `^\d+[dwm]?$` (e.g. `5d`, `14d`, `2w`, `1m`):
   - Convert to days: `Nd` → N, `Nw` → N×7, `Nm` → N×30
   - This becomes `max_age_days` for hiring-post filtering.
2. **Label token** — anything else:
   - `india` → label `india`, set `locations: ["India"]`
   - `founding` → label `founding`, prepend `["Founding Engineer", "Founding ML Engineer", "First AI Hire"]` to `jobRoles`
   - `remote` → label `remote`, add `Remote` to `keywords`, broaden `locations` to `["United States", "Worldwide", "Remote"]`
   - otherwise → label is the lowercased token, default scope params

### Defaults
- No window token → `max_age_days = 14`
- No label token → `label = "us-ai"` and default scope params
- Both missing → `5d` window with `us-ai` label

Echo at start:
```
[mode: hire-search] [label: founding] [max_age: 5d] [sources: apt_marble/linkedin-hiring-posts-scraper + linkedIn-recruiter-scraper]
```

## Execute

### Step A — call the hiring-posts scraper

`mcp__Apify__call-actor` with `actor: "apt_marble/linkedin-hiring-posts-scraper"`:
```json
{
  "hiringKeywords": ["we are hiring", "looking for", "now hiring", "join our team"],
  "jobRoles": ["AI Engineer", "LLM Engineer", "Machine Learning Engineer",
               "Founding Engineer", "Applied AI Engineer", "Agentic AI Engineer",
               "Forward Deployed Engineer"],
  "keywords": ["AI", "LLM", "agentic", "RAG"],
  "locations": ["United States"],
  "maxResults": 200,
  "language": "en",
  "deduplicateResults": true
}
```
`callOptions: { memory: 1024, timeout: 600 }`, `previewOutput: false`.

Apply label-specific adjustments per the Parse step above.

### Step B — call the recruiter scraper

`mcp__Apify__call-actor` with `actor: "apt_marble/linkedIn-recruiter-scraper"`:
```json
{
  "recruiterTitles": ["Technical Recruiter", "AI Recruiter", "Engineering Recruiter",
                      "Talent Acquisition", "Founding Team Recruiter",
                      "Head of Talent", "Talent Lead"],
  "keywords": ["AI", "machine learning", "LLM", "agentic"],
  "locations": ["United States"],
  "maxResults": 200,
  "language": "en",
  "deduplicateResults": true
}
```

### Step C — fetch full datasets

`mcp__Apify__get-actor-output` for each → wrap as `{"items": [...]}` → save to
`~/.job_search/raw_hires/<date>_<label>_hiring_posts.json` and `~/.job_search/raw_hires/<date>_<label>_recruiters.json`.

### Step D — score + write hires.js + archive

```bash
python "scripts/hire_search.py" \
  --hiring-posts "<path A>" \
  --recruiters   "<path B>" \
  --today "$(date -I)" \
  --label "<label>" \
  --max-age-days <N>
```

The script:
- Decodes LinkedIn activity IDs to post creation dates (`id >> 22` = unix seconds)
- Drops posts older than `--max-age-days`
- Recruiters bypass the date filter (standing presence)
- Cross-refs companies against `jobs_ui/data.js` (badge + score boost on match)
- Filters `Frontend Developers` niche
- Dedups against `state.seen_hire_ids` and within-run
- Scores 0–100 (company / role / title / intent / location)
- Appends session to `hires.js` (newest first)

### Step E — relay

Print the script's stdout verbatim. Then:

```
✅ Done. Open in browser: file:///E:/_Resume-Curator/job_search/jobs_ui/hires.html
```

## Rules

- **Never fabricate.** Actor errors → surface verbatim.
- **Allowlist:** only the two `apt_marble/*` actors.
- **Cost ceiling ~$1.00 per run** (200 × $0.0025 × 2 actors).
- **Do not regenerate `jobs_ui/hires.html`.** Static asset.
- **Append-only `hires.js`.** Same session id (date + label) overwrites in place.

## Examples

- `/hire-search` → `us-ai` scope, 14-day post window
- `/hire-search 5d` → `us-ai` scope, 5-day post window
- `/hire-search 5d founding` (or `founding 5d`) → founding-engineer scope, 5-day window
- `/hire-search 7d india` → India scope, 7-day window
- `/hire-search remote` → remote scope, 14-day default window
