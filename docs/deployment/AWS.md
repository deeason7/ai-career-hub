# AWS operations reference

[Deployment guide](../../DEPLOYMENT.md) · [Infrastructure inventory](../../INFRASTRUCTURE.md)

**Standby only.** The public demo uses managed hosting. The AWS compute/database
stack was deprovisioned in July 2026. These procedures apply after an explicit
restoration and validation; they do not describe an available live environment.
Retained DNS zones or backups may cost money. Historical boot times and estimates
are not current guarantees.

## Restore deliberately

1. Inventory retained resources and billing in the AWS account. Confirm the database
   snapshot, hosted zone, ECR repositories, IAM roles and network configuration.
2. Restore PostgreSQL into a private subnet; provision the EC2 host and least-privilege
   instance role. Verify SSM access, ECR pulls and outbound connectivity.
3. Restore secrets under `/portfolio/careerhub/`. Use scoped identity credentials;
   the GitHub job expects an OIDC role through `AWS_ROLE_ARN`, not a new static key.
4. Review `docker-compose.prod.yml`, configure a nonempty Redis password, restore
   certificates and confirm the host paths mounted by nginx.
5. Deploy a tested image, apply migrations with a database backup, and verify API,
   frontend and dependency readiness before restoring public DNS.
6. Reinstall optional wake/sleep schedules only after their resource IDs, roles and
   effects have been reviewed. Enable `AWS_DEPLOY_ENABLED=true` last.

The scripts are operating tools, not a complete declarative infrastructure definition.
Some resources and credentials require separate provisioning. Never assume flipping
the repository variable reconstructs the environment.

## Deployment and rollback

The normal route is the protected branch/PR flow in [CONTRIBUTING](../../CONTRIBUTING.md).
The AWS job builds the API/frontend images, pushes them to ECR and deploys through
SSM. Run manual operations only against a restored environment with a tested commit.
A manual fallback does not waive CI or migration checks.

```sh
# On the restored EC2 host, from the checkout:
bash infra/scripts/pull-secrets.sh
bash infra/scripts/deploy.sh

# Roll back to a previously verified image, using the script's required SHA:
bash infra/scripts/rollback.sh <previous-sha>
```

Read each script's current usage and environment requirements before running it.
A code/image rollback does not undo a database migration automatically.

## Optional scheduling and wake page

| Asset | Responsibility |
|---|---|
| `infra/scripts/start.sh`, `stop.sh` | Start/stop the configured compute/database |
| `infra/scripts/setup-business-hours.sh` | Install business-hours schedules |
| `infra/scripts/schedule-sleep.sh` | Schedule idle stop |
| `infra/scripts/setup-wake-on-visit.sh` | Provision the wake-page/Lambda path |
| `infra/scripts/install-boot-deploy.sh` | Install the boot deployment service |
| `infra/wake-page/` | Public wake page and Lambda controller |

A stopped EC2/RDS environment and a deprovisioned one are different states. Wake
scripts can start existing resources; they cannot restore deleted resources.
The historical flow is DNS failover → CloudFront/S3 page → Lambda → compute/database
start → application health → redirect. See the infrastructure reference for topology.

## TLS, logs and retention

The AWS nginx configuration is `infra/nginx/nginx.conf`; local development uses
`nginx/nginx.dev.conf`. Restore valid certificates before starting the TLS proxy.
After certificate renewal, reload nginx through the production Compose service.
Container logs use the configured CloudWatch groups; verify current retention and
access policy. Sentry is optional.

The document-cleanup helper is `infra/scripts/lifecycle_cleanup.sh`. Confirm its
scheduler, secret configuration and result logging. SQL expiration is not proof that
all derived vectors, accounts, backups or logs were erased; see [SECURITY](../../SECURITY.md).
