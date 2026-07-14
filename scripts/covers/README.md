# Cover-letter files

Three prebuilt PDF covers ship here. `/apply` picks one based on the role title and JD keywords, then attaches the PDF directly to the ATS's cover-letter upload field.

| File | Default for |
|---|---|
| `Cover_Letter_PPM_AI.pdf` | AI / LLM / Agentic / Applied AI / Research / Founding Engineer roles — **the default** |
| `Cover_Letter_PPM_ML.pdf` | Pure ML / MLOps / ML Platform / Deep Learning Engineer roles |
| `Cover_Letter_PPM_FullStack.pdf` | Full-Stack / Backend / Forward Deployed / SWE (non-AI-first) roles |

## Selection rule (used by `/apply`)

Ordered — first matching rule wins:

1. Title contains any of: `full stack`, `full-stack`, `fullstack`, `backend`, `forward deployed`, `fde`, `swe`, `software engineer` (without `ai`/`ml` qualifier) → **FullStack**
2. Title or first paragraph of the JD contains: `mlops`, `ml platform`, `ml infrastructure`, `deep learning engineer`, `data scientist`, `applied ml` (no `ai`/`llm`) → **ML**
3. Otherwise → **AI** (default; covers all agentic/LLM/founding/research/applied-AI roles)

Config for these rules lives in `~/.job_search/answers.json` under `documents.cover_letter_selection`. Edit there — this README is documentation only.

## Adding or replacing a template

Drop a new PDF here with a clear filename. Add it to `answers.json → documents.cover_letters` and either (a) extend the selection rules or (b) point `documents.default_cover` at it. The PDFs themselves are gitignored (per `.gitignore`) — nothing personal ever hits the public repo.

## What `/apply` does NOT do

- Does **not** rewrite the cover letter per role. If the ATS also has a free-text "why this role" question, that's handled separately by the voice memory (`job_search_apply_voice.md`) — plain, short, non-glaze, JD-tailored 2-4 sentences.
- Does **not** convert between formats. PDF in, PDF attached. If an ATS's cover-letter field is a textarea (rare), that field gets left blank; the "why this role" answer covers it.
