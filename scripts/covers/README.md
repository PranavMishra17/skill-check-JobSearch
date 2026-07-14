# Cover-letter templates

Drop your single generic cover-letter template here as `default.md`. `/apply` will:

1. Load `default.md`
2. Do minimal template substitution — `{{company}}`, `{{role_title}}` — leave everything else as-is.
3. Attach as `Cover Letter.pdf` (converted at run time) or paste into the cover-letter textarea, depending on the ATS.

**Do not write role-family variants.** The user specified one template only. `/apply` handles anything JD-specific through the "why this role" and "why us" answer generation, following the voice rules in `job_search_apply_voice.md` in the persistent memory.

## Template variables

Only these are substituted:

- `{{company}}` — the company name
- `{{role_title}}` — the exact job title from the listing

Everything else is left literal. Do not add other placeholders.

## Example structure (yours can differ)

```markdown
Hi {{company}} team,

I'm applying for the {{role_title}} role.

Currently I'm the founding LLM engineer at alfred_ (Techstars-backed, 5,000+ active users), where I own the multi-agent decision layer and the working-memory pipeline. Prior to that I shipped a customer-facing CMS at WheelPrice (10-20K DAU). I have three first-author papers in multi-agent LLM systems and RAG, including one accepted at IEEE CAI 2026.

I'd like to bring that work to {{company}}.

— Pranav
```

Keep it short. Recruiters skim.
