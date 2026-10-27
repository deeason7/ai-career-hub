# ADR-0001: Dual-path LLM — Groq in production, Ollama in dev

- **Status:** Accepted
- **Date:** 2026-04-13

**Implementation clarification — 2026-10-26:** the hosted model is now configured as
`openai/gpt-oss-20b`. Groq with instructor remains the preferred structured path.
The shared structured client also supports Ollama's OpenAI-compatible endpoint;
legacy generation paths use LangChain. Resume parsing can fall back to a legacy
LangChain Groq call before reporting `parse_failed`. A fallback only works when its
provider and model are available; it is not a guarantee of successful generation.

## Context

The product depends on an LLM for cover letters, QA review, skill-gap analysis, and the agent. Production
needs a fast, reliable, structured-output model, but local development must work with no API key, no cost,
and no network dependency. A single provider can't satisfy both.

## Decision

Branch every LLM feature on the computed `USE_GROQ` flag:

- **Production** uses **Groq** (originally LLaMA 3.1 8B Instant) through `instructor`, returning Pydantic-validated
  schemas.
- **Local development** uses **Ollama** (`llama3.2:3b`) through LangChain, with unstructured output.

The Groq path also falls back to Ollama when structured validation fails, so a bad generation degrades
instead of erroring.

## Consequences

- Contributors can use a local model without a cloud key after downloading its weights
  and the application's dependencies.
- Validated structured output protects the database in production (see [ADR-0003](./0003-structured-output-instructor.md)).
- Two code paths must be kept in step, and behaviour differs slightly between them — the fallback is the
  pressure-release valve.

## Alternatives considered

- **Single cloud provider.** Simpler, but no zero-cost local path and a hard external dependency for tests.
- **Single local model.** Free, but too weak/slow for production quality and structured reliability.
