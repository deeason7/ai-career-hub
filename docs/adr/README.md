# Architecture Decision Records

[Documentation](../README.md) · [Architecture](../ARCHITECTURE.md) · [Refactoring plan](../REFACTORING_PLAN.md)

Why does the product work this way? These records explain the choices behind
generation, progress updates, fit feedback, and editable drafts, including their costs.

The format is lightweight [MADR](https://adr.github.io/madr/). Preserve the original
date and decision. Dated implementation clarifications can correct drift; a changed
architectural decision requires a new record that supersedes the old one.

Reviewed against the code on 2026-10-26. Provider settings and deploy status belong in
[configuration](../CONFIGURATION.md) and [project status](../PROJECT_STATUS.md),
so an old provider/model choice here is not an uptime claim.

All five decisions are accepted. Their original dates and subsequent clarifications
remain inside each record.

| Decision | What it enables | Tradeoff to understand |
|---|---|---|
| [0001: Groq and Ollama](0001-dual-path-llm.md) | Hosted generation and a local provider option | Two provider paths need compatibility checks; schemas cannot guarantee equivalent output |
| [0002: Accept work, then poll](0002-async-task-pattern.md) | Progress feedback while longer tasks run | Redis stores task state; in-process execution does not survive a restart |
| [0003: Structured model output](0003-structured-output-instructor.md) | Validate generated fields before displaying or storing them | A valid response shape does not prove its claims are true |
| [0004: Hybrid fit scoring](0004-hybrid-ats-scoring.md) | Explain fit through semantic, keyword, and structure signals | Weights and model behavior need evaluation; the score does not predict hiring outcomes |
| [0005: Revision lineage](0005-refine-lineage-adjacency-list.md) | Trace how a cover letter changes across refinements | Parent-child relationships require ownership, deletion, and completion-state handling |
