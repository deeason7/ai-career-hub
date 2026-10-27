# Documentation

[Project home](../README.md)

Start with the user workflow, then choose the reference for the task at hand.
Each topic has one primary document; historical release details live in the changelog.

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
| [AWS infrastructure reference](../INFRASTRUCTURE.md) | Understand the hibernated AWS target before a separately planned restoration |
| [AWS operating procedures](deployment/AWS.md) | Consult the retained deployment and wake/sleep procedures when working on that optional target |
| [Alternative scheduler](../infra/keep-warm/README.md) | Inspect the optional Cloudflare keep-warm worker and its operational limits |

## Keep references current

Product capabilities belong in the product brief; measurements need a date, method,
and sample size in the status/evaluation documents. Endpoint or environment changes
must update the corresponding API/configuration reference. Release notes record
historical behavior; operating guides describe the current deployment.
