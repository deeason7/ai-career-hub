# AI Career Hub documentation

[Project home](../README.md) · [Try the demo](https://deeason-career.streamlit.app)

**From a job posting to a reviewed application and a clear next step.**

New here? Follow the [first-application walkthrough](../README.md#try-your-first-application)
with synthetic sample data. For a local workspace, start with
[setup and troubleshooting](../CONTRIBUTING.md#running-locally).

Each topic below has one primary guide. The status and checkpoint pages distinguish
the deployed release from verified, unreleased changes; the changelog preserves history.

## Understand the product

| Document | Use it to |
|---|---|
| [Product brief](PRODUCT.md) | Understand the candidate's problem, current workflow, product boundaries, and how user value will be measured |
| [Project status](PROJECT_STATUS.md) | Check what was verified, which release is deployed, and what remains before a new release |
| [Cleanup checkpoint](CHECKPOINT.md) | Review the cleaned baseline, verification results, and unresolved gates |
| [Refactoring plan](REFACTORING_PLAN.md) | Connect the next engineering changes to completed application workflows and measurable user value |
| [Changelog](../CHANGELOG.md) | Read the versioned history without treating old deployment details as current instructions |

## Build and integrate

| Document | Use it to |
|---|---|
| [Contributing](../CONTRIBUTING.md) | Set up the local stack, run checks, and follow the branch/review workflow |
| [Backend guide](../backend/README.md) | Navigate the API implementation and its development entry points |
| [Architecture](ARCHITECTURE.md) | Trace requests, asynchronous work, application data, and model dependencies |
| [API reference](API.md) | Find routes, payloads, authentication, task polling, and response contracts |
| [Configuration](CONFIGURATION.md) | Configure the database, model providers, storage, and runtime flags |
| [Architecture decisions](adr/README.md) | Understand the tradeoffs behind the established design |
| [Evaluation guide](../backend/evals/README.md) | Reproduce scoring benchmarks and interpret their limits |

## Operate and protect

| Document | Use it to |
|---|---|
| [Deployment and recovery](../DEPLOYMENT.md) | Run the active hosted deployment, verify readiness, and recover sleeping services |
| [Security](../SECURITY.md) | Review controls, known limitations, and vulnerability-reporting instructions |
| [Dependency review](DEPENDENCY_REVIEW.md) | Review dated package findings, the JWT fix, and the remaining security release gate |
| [AWS infrastructure reference](../INFRASTRUCTURE.md) | Understand the deprovisioned AWS target before a separately planned restoration |
| [AWS operating procedures](deployment/AWS.md) | Consult the retained deployment and wake/sleep procedures when working on that optional target |
| [Alternative scheduler](../infra/keep-warm/README.md) | Inspect the optional Cloudflare keep-warm worker and its operational limits |

## Keep references current

Product capabilities belong in the product brief; measurements need a date, method,
and sample size in the status/evaluation documents. Endpoint or environment changes
must update the corresponding API/configuration reference. Release notes record
historical behavior; operating guides describe the current deployment.

Run `make docs-check` from the repository root after editing. It checks local Markdown
links, heading anchors, and the five current release markers. Keep the latest release
summary in the root README and the complete history in CHANGELOG.
