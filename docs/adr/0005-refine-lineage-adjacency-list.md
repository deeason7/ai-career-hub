# ADR-0005: Refinement lineage as an adjacency list

- **Status:** Accepted
- **Date:** 2026-06-12

## Context

A user can branch a new cover-letter refinement from *any* past revision, not just the active text. The
schema has to record which revision a branch was forked from, but the UI only ever renders flat, labelled
lists (`v4 ← v2`), not arbitrary subtree queries.

## Decision

Add a single nullable self-referencing foreign key, `parent_revision_id`, to `cover_letter_revisions`, with
`ON DELETE SET NULL`. `NULL` means "refined from the active letter"; a non-null value points at the revision
the branch came from. Version numbers stay a single flat, lock-serialised sequence; lineage is a tree
layered on top of that sequence.

## Consequences

- Minimal schema (one column) and simple writes.
- Deleting an ancestor degrades its children to unlabelled roots instead of blocking the delete or
  cascading a whole branch away.
- Subtree queries would need a recursive CTE — acceptable, because the product never asks for them. No
  index on the parent column, since per-letter revision counts are tiny.

## Alternatives considered

- **A dedicated edges table.** Overkill for strictly single-parent lineage.
- **Materialised path / closure table.** Fast subtree reads, but heavier writes for a feature that never
  queries subtrees.
- **Tracking an `active_revision_id` pointer.** A larger semantic change for little real UI gain.
