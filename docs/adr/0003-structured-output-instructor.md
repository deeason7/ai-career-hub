# ADR-0003: Structured LLM output via instructor + Pydantic

- **Status:** Accepted
- **Date:** 2026-04-13

**Implementation clarification — 2026-10-26:** schema validation checks types, required
fields and declared bounds. A well-formed false claim can still pass. The QA reviewer
and user review are separate factual checks; the reviewer's agreement with human
labels has not yet been calibrated.

## Context

LLMs emit free text, but the application persists structured records — cover letters with QA scores, skill
recommendations, extracted job metadata. A malformed field should be rejected before persistence,
and ad-hoc parsing of model output is brittle.

## Decision

Use `call_structured()` as the preferred production interface. It uses **`instructor`** to coerce the
response into a Pydantic v2 schema from `services/llm_schemas.py`, retrying on validation failure. The
schema is the contract; only validated objects reach application code.

## Consequences

- Deterministic, typed contracts — no regex parsing, no surprise shapes.
- Validation rejects malformed schema fields; it does not establish factual accuracy.
- Retries cost some latency and tokens, and schema changes must be coordinated with prompts.

## Alternatives considered

- **Regex / hand-rolled JSON parsing.** Brittle and breaks silently as model output drifts.
- **Provider function-calling, raw.** Still needs validation and retry glue; `instructor` is that glue.
- **No validation.** Fastest, and unacceptable — it lets bad data persist.
