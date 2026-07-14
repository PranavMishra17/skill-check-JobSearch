# alfred_ — Founding LLM Engineer

**Role:** Founding LLM / AI Engineer
**Dates:** April 2026 — Present
**Location:** New York City, NY
**Company:** alfred_ — Techstars-backed consumer AI executive assistant. A multi-agent LLM system that manages a user's email, calendar, and daily obligations over SMS, web chat, and voice.
**Scale:** **5,000+ active users** in production (up from ~2K at May 2026); hundreds of paying subscribers; live multi-account email (Gmail + Outlook), calendar, and SMS pipelines running 24/7.

> Résumé-facing summary of my work at alfred_. Written for readers outside the company — recruiters, hiring managers, and engineers on other teams. High-level design (HLD) first, with enough technical specificity to be verifiable, and internal codenames translated into plain terms.

---

## 1. Role shape

Founding-team engineer at a Techstars-backed consumer-AI startup, working directly with the founder/CEO and a small core team. I own **vertical slices end to end**: design → build → ship to production → measure → iterate on real user data. My work spans three layers that most companies split across separate teams:

- **Agent infrastructure** — the multi-agent orchestration, tool-calling, and decision logic that decides what the assistant does on each user's behalf.
- **The product's core value features** — the email-automation layer (rules, notifications, drafting) and a per-user "working memory" system.
- **Production reliability & observability** — evaluation harnesses, an automated production-failure scanner, cost engineering, and daily metrics that keep a live agent trustworthy at scale.

Almost everything below is **shipped and running in production for real users**, not prototype work.

---

## 2. What I own and have built

### 2.1 Multi-agent orchestration & the Execution Decision Layer
The assistant runs as a multi-agent system over a TypeScript/Deno backend: an inbound message (SMS or web) is routed through intent classification, a decision layer, and a set of callable tools (send email, draft a reply, create a calendar event, set a rule, etc.).

- Maintain **tool-calling reliability under production load** — the layer must behave deterministically across thousands of daily agent turns, with correct behavior on retries, partial failures, and provider errors (Gmail/Outlook APIs differ subtly and fail differently).
- Built and hardened the **Execution Decision Layer**: every candidate action is classified into one of five verdicts — **SILENT / NOTIFY / CONFIRM / CLARIFY / REFUSE** — using **deterministic risk scoring rather than an LLM-as-judge**, so the decision is repeatable, auditable, and fast. Includes a pending-obligations queue (actions resurface when context warrants) and a bounded **undo window** for recovering side effects.
- Added **anti-fabrication guarantees**: guards that stop the agent from claiming it took an action, searched a store, or has a capability when the underlying tools didn't actually run — grounded against the real tool-execution ledger for that turn.

### 2.2 Working Memory — durable per-user memory with structural anti-hallucination
Designed and shipped a **per-user "working memory"**: a continuously reconciled store of a user's open and closed "loops" (things they owe, things owed to them, projects, deadlines) distilled from their email and calendar.

- **The hard problem was trust.** An LLM summarizing an inbox will confidently invent threads, invert who owes the next move, or show a closed loop as still open. I re-architected the pipeline into a **strict-ID design**: the language model only *selects* from a menu of real candidates behind opaque handles and writes prose — it never emits or echoes an identifier or ownership field. All identity, ownership, and closed-state data is re-attached by code. This makes a whole class of hallucination **structurally impossible rather than probabilistically reduced**, and is enforced by tests.
- Built the ingestion + ranking substrate: live provider fetch (Gmail Graph + IMAP), a map-reduce summarization path that scales with inbox volume, direction-aware ownership (comparing message senders against the user's own addresses), and an importance model driven by *behavior* (a personal-PageRank-style signal over correspondents) rather than the email's self-description.
- Wired working memory into the **live agent** as a progressive-disclosure lookup tool (search → compact state → drill in), reaching both the SMS and web surfaces, and into an admin monitoring view.
- Ran a rigorous **ground-truth audit loop**: grading real generated briefs against live inboxes to catch fabrication / owner-inversion / closed-shown-open defects, then fixing and re-auditing — the discipline that took the feature from "impressive demo" to "safe to send."

### 2.3 Email automation layer (the product's core loop)
Own large parts of how alfred_ actually *acts* on email for users:

- **Rules engine** — users create email rules in plain language from chat (~98% of rules are chat-created); I built the matcher, the action vocabulary (notify, archive, label, move, forward, auto-draft, suppress-draft with custom tone), compound rules, and a **verify-after-edit safety net** that warns when a new rule matches none of the user's recent mail (closing a class of "the assistant said my rule works, but it silently matched nothing" failures).
- **Email → action extraction** — pulling to-dos, calendar events, and security/OTP signals out of inbound mail, then surfacing or executing them with confirmation and verification.
- **Email → SMS notification pipeline** — and a latency win I'm proud of: notifications were arriving **~90 seconds** after an email (the delay was a polling timer, not compute). I moved delivery to an **instant event-trigger the moment a notification is queued**, with the old cron demoted to a safety backstop — cutting delivery to **~3 seconds (≈30×)** while suppressing nothing, then extended the same fix to the security/OTP and flight-alert paths (which had been ~189s at p90).
- **Notification precision** — fixed a cluster of correctness bugs (an OTP detector false-firing on URL-encoded tracking links; one email producing two texts; the agent naming the wrong rule as the cause) and shipped a read-only "why was I notified" provenance tool so the assistant can explain a notification instead of guessing.

### 2.4 Production reliability, evaluation & observability
- **Deterministic eval harness** for the agent surfaces — trace replay, fixture-driven scenarios, and scoring across the five verdict types, with regression detection on tool-calling reliability and decision-layer outputs.
- **Automated production-failure scanner** — a pipeline that scans real production conversations, classifies genuine agent failures vs. expected behavior, auto-promotes real bugs for triage, and fans out per-failure investigation. I continually tune its **precision** (e.g., teaching it that a one-way notification expecting no reply isn't an "abandoned" conversation, and joining against the real tool-execution record to stop false "the agent did nothing" flags).
- **Email Work Layer daily metrics** — a nightly analytics + observability system: one consolidated service query behind the numbers, day-over-day / week-over-week / seasonal movement, adoption and reliability panels, and an emailed executive brief. Built with care around real analytics traps (e.g., never showing a cross-week delta on a retention-swept table that would fake a spike).

### 2.5 LLM cost engineering
Led the investigation and re-architecture of **LLM inference cost** for the background email-processing pipeline (the dominant spend). Instrumented per-model, per-stage spend; identified the real drivers (triage classification volume × reasoning-token budget) versus red herrings; and shipped levers — a dead-model deprecation alarm, reasoning-budget tuning gated behind evaluation, and cheaper-tier routing for low-stakes mail.

### 2.6 Data & platform
- **Postgres at production scale** — schema design for a source-agnostic memory store (hardened up front with an adversarial design review: correct identity keys, TOAST/autovacuum tuning, partial indexes scoped to the working set), plus idempotent, collision-safe migrations.
- **Security** — row-level security and `SECURITY DEFINER` RPC hardening, including catching and fixing a **cross-user data-leak** class on new agent-facing read functions (default `PUBLIC` execute grants).
- **Push-based ingestion** — moving pieces of the system off DB polling toward event-driven processing for sub-second responsiveness.

### 2.7 Onboarding integration (take-home → production)
Before joining full-time, designed and prototyped the alfred_ Execution Decision Layer as a take-home (Next.js 14, TypeScript, MCP tool execution, Cartesia TTS for voice, deployed on Vercel). That decision-layer design became the production pattern described in §2.1.

---

## 3. Selected impact

- **Scaled with the product** from ~2K to **5,000+ active users** while the surface area (email rules, working memory, notifications, drafting) grew substantially.
- **Notification latency ~90s → ~3s (≈30×)** by replacing polling with event-triggered delivery; extended to the security/OTP path (189s p90 → instant).
- **Eliminated a class of agent hallucination structurally** (fabricated references / inverted ownership) via the strict-ID working-memory pipeline — provable, not probabilistic.
- **Automated production-failure triage** — a scanner that turns thousands of live conversations into a ranked, de-duplicated bug queue, replacing manual log-reading.
- **Cut and instrumented LLM inference cost** on the highest-spend pipeline, with evaluation-gated rollout so cost cuts don't regress quality.
- Shipped **dozens of production PRs across a ~3-month span** — features, reliability fixes, migrations, and observability — on a live system with real paying users.

---

## 4. Stack

TypeScript / Node.js / Deno · multi-agent orchestration · MCP tool execution · LLM APIs (Claude, Gemini) with prompt/eval engineering · Postgres (Supabase) with RLS + pg_cron · Gmail/Graph/IMAP + calendar integrations · React/Vite admin & monitoring UIs · Cartesia TTS (voice) · Vercel · deterministic risk-scoring & evaluation infrastructure.

---

## 5. The Decision Layer (reference detail)

Five verdicts over each candidate action:
- **SILENT** — no user-facing action.
- **NOTIFY** — informational ping (no confirmation needed).
- **CONFIRM** — high-trust / side-effecting action; user confirms before commit.
- **CLARIFY** — ask the user to disambiguate intent.
- **REFUSE** — out of policy / too risky.

Deterministic risk scoring (not LLM-as-judge) → repeatable, auditable, fast. MCP tool-execution layer. Pending-obligations queue (actions resurface when context warrants). Bounded undo window for time-limited recovery of side effects. Anti-fabrication guards grounded on the real tool-execution ledger.

---

## 6. Role-targeting

- **Agentic AI / LLM Engineer** — founding-team, production multi-agent system with a real eval harness, anti-hallucination architecture, and cost engineering. Directly transferable.
- **Forward-Deployed / Founding Engineer** — full vertical-slice ownership, take-home-to-production trajectory, Techstars context, comfort shipping to a live user base.
- **Evaluation / ML-Platform / Trust & Safety** — deterministic eval harness, automated production-failure scanning, ground-truth audit loops, regression detection.
- **Voice AI** — Cartesia TTS integration and real-time pipelines.

## 7. Tags

`agentic-ai` `production-shipped` `multi-agent` `evaluation-harness` `llm-observability` `anti-hallucination` `cost-engineering` `mcp` `voice-ai` `postgres` `founding-team` `typescript`

## 8. One-liner pitches

- **Generic AI Eng:** "Founding LLM engineer at a Techstars-backed AI assistant serving 5,000+ users; I own multi-agent orchestration, a per-user working-memory system with structural anti-hallucination, and the eval/observability stack."
- **Agentic AI cut:** "Built a five-verdict execution decision layer with deterministic risk scoring, and re-architected the assistant's memory into a strict-ID pipeline that makes LLM fabrication structurally impossible — provable by tests, not vibes."
- **Reliability / platform cut:** "Cut email→SMS notification latency ~30× (polling → event-triggered), automated production-failure triage over thousands of live conversations, and instrumented + reduced LLM inference cost on the highest-spend pipeline."
- **FDE cut:** "Shipped the decision layer as a Vercel-deployed take-home before joining the founding team; now own the agent orchestration, the email-automation layer, working memory, and the evaluation/observability stack end to end for a live paying user base."