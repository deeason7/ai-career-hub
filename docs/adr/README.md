# Architecture Decision Records

This directory records the load-bearing technical decisions behind AI Career Hub — the context, the
choice, and what it cost — so the reasoning survives past the commit that implemented it.

The format is lightweight [MADR](https://adr.github.io/madr/). A record is immutable once accepted; when a
decision changes, a new record supersedes the old one rather than editing history.

| ADR | Decision | Status |
|---|---|---|
| [0001](./0001-dual-path-llm.md) | Dual-path LLM — Groq + `instructor` in production, Ollama in dev | Accepted |
| [0002](./0002-async-task-pattern.md) | Async work via `202` + poll over a Redis task store | Accepted |
| [0003](./0003-structured-output-instructor.md) | Structured LLM output via `instructor` + Pydantic | Accepted |
| [0004](./0004-hybrid-ats-scoring.md) | Hybrid ATS scoring — semantic + keyword + structure | Accepted |
| [0005](./0005-refine-lineage-adjacency-list.md) | Refinement lineage as an adjacency list | Accepted |
