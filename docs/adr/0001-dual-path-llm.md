# ADR-0001: Dual-path LLM — Groq in production, Ollama in dev

- **Status:** Accepted
- **Date:** 2026-04-13

## Context

The product depends on an LLM for cover letters, QA review, skill-gap analysis, and the agent. Production
needs a fast, reliable, structured-output model, but local development must work with no API key, no cost,
and no network dependency. A single provider can't satisfy both.

## Decision

Branch every LLM feature on the computed `USE_GROQ` flag:

- **Production** uses **Groq** (LLaMA 3.1 8B Instant) through `instructor`, returning Pydantic-validated
  schemas.
- **Local development** uses **Ollama** (`llama3.2:3b`) through LangChain, with unstructured output.

The Groq path also falls back to Ollama when structured validation fails, so a bad generation degrades
instead of erroring.

## Consequences

- Contributors run the full stack offline with no key or spend.
- Validated structured output protects the database in production (see [ADR-0003](./0003-structured-output-instructor.md)).
- Two code paths must be kept in step, and behaviour differs slightly between them — the fallback is the
  pressure-release valve.

## Alternatives considered

- **Single cloud provider.** Simpler, but no zero-cost local path and a hard external dependency for tests.
- **Single local model.** Free, but too weak/slow for production quality and structured reliability.
