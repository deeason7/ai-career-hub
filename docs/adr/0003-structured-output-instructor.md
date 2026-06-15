# ADR-0003: Structured LLM output via instructor + Pydantic

- **Status:** Accepted
- **Date:** 2026-04-13

## Context

LLMs emit free text, but the application persists structured records — cover letters with QA scores, skill
recommendations, extracted job metadata. A hallucinated or malformed field must never reach the database,
and ad-hoc parsing of model output is brittle.

## Decision

Route every production LLM call through `call_structured()`, which uses **`instructor`** to coerce the
response into a Pydantic v2 schema from `services/llm_schemas.py`, retrying on validation failure. The
schema is the contract; only validated objects reach application code.

## Consequences

- Deterministic, typed contracts — no regex parsing, no surprise shapes.
- Validation is the gate that keeps malformed/hallucinated data out of the database.
- Retries cost some latency and tokens, and schema changes must be coordinated with prompts.

## Alternatives considered

- **Regex / hand-rolled JSON parsing.** Brittle and breaks silently as model output drifts.
- **Provider function-calling, raw.** Still needs validation and retry glue; `instructor` is that glue.
- **No validation.** Fastest, and unacceptable — it lets bad data persist.
