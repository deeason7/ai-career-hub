# ADR-0004: Hybrid ATS scoring — semantic + keyword + structure

- **Status:** Accepted
- **Date:** 2026-05-16

## Context

A resume-to-job match score has to be both fair and credible. Keyword-only ATS systems miss synonyms and
are easy to game with keyword stuffing; a purely semantic score misses hard must-have terms and ignores
whether the resume is even structured like a resume.

## Decision

Combine three signals into one score:

| Signal | Weight |
|---|--:|
| Semantic similarity (`all-MiniLM-L6-v2`, document + per-section) | 50% |
| Keyword overlap (exact + bigrams + priority bonus, after boilerplate stripping) | 30% |
| Structure heuristics (presence of experience, education, skills…) | 20% |

The sentence-transformers model is loaded once via `@lru_cache` and shared with the embedding service, so
the process holds a single copy.

## Consequences

- A balanced, explainable score that rewards real relevance over keyword stuffing.
- One model instance in memory for both scoring and retrieval.
- The weights are deliberate heuristics, not learned, and semantic scoring adds CPU cost — mitigated by the
  shared singleton and caching.

## Alternatives considered

- **Keyword-only.** Cheap and transparent, but misses synonyms and is trivially gamed.
- **Embedding-only.** Catches meaning, but misses exact must-have terms and resume structure.
- **An LLM as judge for the score.** Flexible, but slower, less deterministic, and costlier per request than
  a cached embedding model.
