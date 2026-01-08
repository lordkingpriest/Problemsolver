# PR Checklist — Problemsolver (Merge Blockers)

Purpose: authoritative, merge-blocking checklist to ensure all code merged into `main` is deployable and auditable for a production money-handling service.

Before merging a PR that touches the backend, poller, charts, or CI, confirm each item below.

CI & Tests
- [ ] CI status is green for all jobs:
  - `test` (unit/integration, migrations, schema-drift check)
  - `helm-servicemonitor-check` (Helm ServiceMonitor contract)
- [ ] Alembic migrations applied cleanly in CI (`alembic upgrade head` in CI)
- [ ] No schema drift reported by `scripts/schema_diff_check.py` (exit 0)
- [ ] Unit tests pass (`pytest`) and cover:
  - Binance signing helper
  - Webhook signing/verification
  - Amount-diff determinism
  - Idempotent deposit ingestion
- [ ] E2E integration tests run successfully in CI or on staging:
  - `tests/e2e/test_e2e_flow.py` (invoice -> mocked deposit -> poller -> ledger + webhook)

Security & Secrets
- [ ] No secrets committed in the PR (search for API keys, tokens, DB credentials).
- [ ] All runtime secrets referenced via environment variables, K8s Secrets, or Vault.
- [ ] New config keys added to `app/core/config.py` are documented and default to `None`.
- [ ] Sentry DSN is only read from env and not committed.
- [ ] README or ops doc references secret rotation runbook and compromised-key steps.

Database & Migrations
- [ ] Alembic migration scripts included for any DB schema changes; migrations are reversible (upgrade & downgrade).
- [ ] `schema.sql` updated and matches Alembic revisions.
- [ ] Migration checksum recorded in PR description (sha256 of migration file).
- [ ] DB model changes in `app/db/models.py` exactly reflect DDL (no drift).
- [ ] New tables have appropriate indexes, UNIQUE constraints, and append-only enforcement where required.

Poller & Processor
- [ ] Poller is the only component that uses Binance API keys.
- [ ] Poller time sync logic present and tested.
- [ ] Processor implements SELECT ... FOR UPDATE and performs payments + ledger writes in a single transaction.
- [ ] deposit_raw.tx_id uniqueness enforced at DB level.
- [ ] Amount-differentiation implemented and configured (AMOUNT_DIFF_K default documented).

Observability
- [ ] Prometheus metrics exported:
  - `problemsolver_deposits_processed_total`
  - `problemsolver_deposits_errors_total`
  - `problemsolver_collisions_total`
  - `problemsolver_poller_last_success_unixtime`
  - `problemsolver_webhook_success_total`
  - `problemsolver_webhook_fail_total`
- [ ] Helm ServiceMonitor contract validated by CI (helm-servicemonitor-check).
- [ ] Grafana dashboard JSON provided and referenced in provisioning.

Kubernetes / Helm
- [ ] Helm charts updated (poller + webhook-worker).
- [ ] `serviceMonitor.enabled` flag documented and default values appropriate.
- [ ] Service exposes a `metrics` named port and metadata label `app: problemsolver-<component>`.
- [ ] Charts include liveness/readiness probes (readiness must check DB connectivity).
- [ ] Resource requests/limits provided.

Operational Readiness
- [ ] Deployment checklist (DEPLOYMENT.md) updated and copy-paste ready.
- [ ] Rollback instructions included (ROLLBACK.md).
- [ ] Runbooks or TODO pointers for:
  - Compromised keys
  - Poller outage & restart
  - Collision resolution
  - Manual settlement process

Audit & Documentation
- [ ] FILES_ADDED.md attached to PR summarizing changed/added files.
- [ ] Migration checksum, schema-diff output, and CI run URL included in PR description.
- [ ] Security & Compliance note included: no auto-withdrawals; manual settlement only until legal signoff.

Approver Checklist
- [ ] I confirm I reviewed DB schema & Alembic migration (approver initials / date)
- [ ] I confirm Prometheus scraping & Grafana import validated in staging (approver initials / date)
- [ ] I confirm secrets management plan reviewed (approver initials / date)

Merging policy: PRs that fail any of the above items are NOT to be merged. This checklist is part of the release gating for production branches.