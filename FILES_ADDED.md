# Files Added / Modified — Problemsolver (Authoritative List)

This file enumerates all new and changed files introduced by the deliverables. Use this list for reviewers and auditors.

Top-level / repo root
- pyproject.toml
- requirements.txt
- Dockerfile
- README.md

Application code (Python)
- app/main.py
- app/api/health.py
- app/api/ready.py
- app/api/invoices.py
- app/core/config.py
- app/core/sentry.py
- app/utils/binance_signing.py
- app/utils/webhook_signing.py
- app/db/session.py
- app/db/models.py
- app/db/poller_models.py
- app/poller/binance_client.py
- app/poller/config.py
- app/poller/amount_diff.py
- app/poller/processor.py
- app/poller/service.py
- app/poller/main.py
- app/webhooks/worker.py
- app/bin/healthcheck.py

Poller & packaging
- poller/Dockerfile
- app/poller/README.md

Migrations / SQL
- schema.sql
- alembic/versions/0001_initial.py
- migrations/README.md

K8s manifests (examples)
- k8s/poller-deployment.yaml
- k8s/webhook-worker-deployment.yaml

Helm charts
- charts/poller/Chart.yaml
- charts/poller/values.yaml (updated / additions)
- charts/poller/templates/deployment.yaml
- charts/poller/templates/servicemonitor.yaml
- charts/poller/templates/servicemonitor-rbac.yaml (optional)
- charts/poller/templates/networkpolicy-servicemonitor.yaml (optional)

- charts/webhook-worker/Chart.yaml
- charts/webhook-worker/values.yaml (updated / additions)
- charts/webhook-worker/templates/deployment.yaml
- charts/webhook-worker/templates/servicemonitor.yaml
- charts/webhook-worker/templates/servicemonitor-rbac.yaml (optional)
- charts/webhook-worker/templates/networkpolicy-servicemonitor.yaml (optional)

- charts/common/templates/servicemonitor-rbac.yaml
- charts/common/templates/networkpolicy-servicemonitor.yaml

Observability / Grafana provisioning
- observability/grafana/provisioning/datasources/problemsolver-prometheus.yaml
- observability/grafana/provisioning/dashboards/problemsolver-dashboard.yaml
- observability/grafana/dashboards/problemsolver-dashboard.json

CI & scripts
- .github/workflows/ci.yml (updated)
- scripts/schema_diff_check.py
- scripts/helm_assert_servicemonitors.sh
- scripts/run_e2e.sh

Tests
- tests/test_binance_signing.py
- tests/test_ingest_idempotent.py
- tests/test_binance_time_sync.py
- tests/test_amount_diff.py
- tests/test_invoice_creation.py (scaffold)
- tests/e2e/test_e2e_flow.py

Other
- PR_CHECKLIST.md
- DEPLOYMENT.md
- FILES_ADDED.md
- ROLLBACK.md (see next file)

Notes
- This list is exhaustive for the current deliverable set. If your repo already had files with these names, please compare file checksums before merge.
- All sensitive values are read from env/secrets; no secrets are present in these files.