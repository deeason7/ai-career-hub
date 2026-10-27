# ADR-0002: Async work via 202 + poll over a Redis task store

- **Status:** Accepted
- **Date:** 2026-06-11

**Implementation clarification — 2026-10-26:** the Redis hash store and inline `200`
fallback below apply to job-match analysis and Quick Apply. Cover-letter generation
always accepts with `202`; its task ID and status are stored in PostgreSQL and polled
from that record, with optional n8n dispatch. Background work runs in the API process
unless n8n handles it, so task progress storage does not make execution durable across
an API restart. Current job-match steps run sequentially to limit provider rate pressure.

## Context

Cover-letter generation, combined job-match analysis, and the agent each make several LLM calls. Holding a
request open for that long times out and dies the moment the user switches pages. Progress also needs to be
visible, and several steps of the job-match fan-out complete independently.

## Decision

Accept the work and return **`202 Accepted`** with a `task_id`; run it in the background; publish progress
to a Redis task store the client polls (`GET …/task/{task_id}`). The store uses **one hash per task with
one field per step**, so concurrent step writers never collide on a shared value. When Redis is
unavailable, the caller runs the work inline and returns a normal `200` — degraded, not broken.

## Consequences

- Async clients can poll progress while remaining navigable; inline fallback holds
  the request until completion and remains subject to request timeouts.
- No read-modify-write races on shared task state.
- The live-progress path needs Redis; without it the feature still works but loses streaming. Polling adds
  some request overhead.

## Alternatives considered

- **Hold the request open.** Simplest, but times out and dies on navigation — the problem we started with.
- **WebSockets / SSE.** Real-time, but adds infrastructure and fights nginx buffering and Streamlit's rerun
  model for little gain over a 2-second poll.
- **A database table for task state.** Durable, but heavier, needs a migration, and adds write load to the
  primary store for ephemeral data.
- **A single JSON blob in Redis.** Simple to read, but parallel step writers race on it.
