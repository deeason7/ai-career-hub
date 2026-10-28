## Summary

<!-- Describe the user problem and resulting behavior. Link any related issue (e.g. Closes #123). -->

## Validation

<!-- Record commands and results, including checks not run. For impact claims, include the baseline, sample size, and measurement method. -->

## Type of change

- [ ] Feature (`feat`)
- [ ] Bug fix (`fix`)
- [ ] Refactor / chore
- [ ] Documentation
- [ ] Security

## Checklist

- [ ] Branch targets `develop` (not `main`)
- [ ] Commits follow Conventional Commits (`type(scope): description`)
- [ ] `ruff check backend/ frontend/` and `ruff format --check backend/ frontend/` pass for code changes
- [ ] Relevant backend/frontend tests pass; behavioral changes include regression coverage
- [ ] `make docs-check` passes; `make test-probes` passes for documentation/release tooling changes
- [ ] Any schema change ships an Alembic migration with a working `downgrade`
- [ ] README / docs updated if behaviour or structure changed
- [ ] Unreleased behavior and measured results are distinguished from the deployed release

## Notes for reviewers

<!-- Tradeoffs, follow-ups, screenshots — anything worth calling out. -->
