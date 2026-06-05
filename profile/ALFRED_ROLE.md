# alfred_ — Founding LLM Engineer (current role)

**Start:** April 2026 — Present
**Location:** New York City, NY
**Company:** alfred_ — Techstars-backed consumer AI executive assistant. Multi-agent LLM workflows over SMS and voice surfaces. **5,000+ active users** (up from 2K+ at May resume snapshot).

## Role shape

Founding-team LLM engineer at a Techstars-backed consumer-AI startup. Vertical-slice ownership: design → ship → measure. Small founding team (Dinesh, Sameer, Connor, Denise). The work is half infrastructure (TypeScript backend, orchestration, tool reliability) and half evaluation/observability (eval harness, regression detection, decision-layer auditability).

## What I'm building

- **Eval harness for the SMS agent surface (current focus).** Deterministic, repeatable evaluation pipeline. Trace replay, fixture-driven scenarios, scoring across verdict types (SILENT / NOTIFY / CONFIRM / CLARIFY / REFUSE), regression detection on tool-calling reliability and decision-layer outputs.
- **Multi-agent orchestration + tool-calling stability** in the TypeScript backend. Decision layer (risk scoring, MCP tool execution, pending obligations, undo window) must behave deterministically under production load.
- **Low-latency context retrieval** across real-time pipelines feeding the agent.
- **Onboarding integration:** designed and prototyped the alfred_ Execution Decision Layer as a take-home (Next.js 14, TypeScript, MCP, Cartesia TTS, Vercel) prior to joining full-time.

## Stack

TypeScript, Node.js, multi-agent orchestration frameworks, MCP tool execution, Cartesia TTS (voice surface), deterministic risk-scoring layer, evaluation infrastructure.

## Decision Layer (take-home → production)

Five verdict types over candidate actions:
- **SILENT** — no user-facing action
- **NOTIFY** — informational ping
- **CONFIRM** — high-trust action; human confirms before commit
- **CLARIFY** — ask user to disambiguate
- **REFUSE** — out of policy / risk

Deterministic risk scoring (not LLM-as-judge) — repeatable, auditable, fast. MCP tool execution layer. Pending obligations queue (actions surface back when context warrants). Undo window for bounded-time recovery of side effects.

## Why this matters for role-targeting

- **Agentic AI / LLM Engineer roles:** founding-team production multi-agent system with eval harness — directly transferable.
- **Forward Deployed / Founding Engineer roles:** full vertical-slice ownership, take-home-to-production trajectory, Techstars context.
- **Voice AI roles:** Cartesia TTS integration, real-time pipelines.
- **Evaluation infra / ML platform roles:** deterministic eval harness for production agent, regression detection.

## Tags

`agentic-ai` `production-shipped` `evaluation-harness` `voice-ai` `mcp` `founding-team` `multi-agent` `typescript`

## One-liner pitches

- *Generic AI Eng:* "Founding LLM engineer at a Techstars-backed AI assistant; building eval harness and multi-agent orchestration for 5K+ active users."
- *Agentic AI cut:* "Designed five-verdict execution decision layer with deterministic risk scoring and MCP tool gating; now building eval infrastructure for the production agent."
- *FDE cut:* "Shipped the decision layer as a Vercel-deployed take-home prior to founding-team join; now own the eval harness, orchestration reliability, and context-retrieval pipelines end-to-end."
