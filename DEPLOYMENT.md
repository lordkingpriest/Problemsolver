# Deployment & Post-Deploy Validation — Problemsolver (Production-Ready)

This document contains exact, copy-paste commands and checks to build, push, deploy, and validate Problemsolver components (Poller and Webhook Worker) to Kubernetes using Helm. Replace placeholders before executing.

WARNING: do NOT commit secrets to git. Use Vault, sealed-secrets, or Kubernetes Secrets.

---

## Conventions & placeholders
- REGISTRY — your container registry (e.g., ghcr.io/org, docker.io/org, registry.example.com)
- TAG — image tag (e.g., v1.0.0, ci-${GITHUB_RUN_ID})
- NAMESPACE — Kubernetes namespace (default: `default`)
- HELM_RELEASE_POLLER — helm release name for poller (default: `problemsolver-poller`)
- HELM_RELEASE_WEBHOOK — helm release name for webhook worker (default: `problemsolver-webhook`)
- SECRET_NAME — Kubernetes secret holding runtime secrets (default: `problemsolver-secrets`)

---

## 1) Build images (local or CI)
# Poller
docker build -t REGISTRY/problemsolver-poller:TAG -f poller/Dockerfile .
docker push REGISTRY/problemsolver-poller:TAG

# Webhook worker
docker build -t REGISTRY/problemsolver-webhook-worker:TAG -f poller/Dockerfile .
docker push REGISTRY/problemsolver-webhook-worker:TAG

Notes:
- Use CI to build images and publish immutable tags (e.g., CI build number + commit SHA).
- Scan images for vulnerabilities (SCA) before pushing to prod registry.

---

## 2) Prepare Kubernetes secrets (do not store in repo)
kubectl create secret generic SECRET_NAME \
  --namespace NAMESPACE \
  --from-literal=DATABASE_URL='postgresql://postgres:REDACTED@db.example.com:5432/postgres' \
  --from-literal=BINANCE_API_KEY='REDACTED' \
  --from-literal=BINANCE_API_SECRET='REDACTED' \
  --from-literal=WEBHOOK_SECRET='REDACTED' \
  --from-literal=SENTRY_DSN='REDACTED' \
  --from-literal=REDIS_URL='redis://:REDACTED@redis.example.com:6379/0'

Recommended: use Vault + ExternalSecrets operator or SealedSecrets to avoid plaintext secrets in cluster manifests.

---

## 3) Helm install / upgrade
# Poller
helm upgrade --install HELM_RELEASE_POLLER charts/poller \
  --namespace NAMESPACE \
  --set image.repository=REGISTRY/problemsolver-poller \
  --set image.tag=TAG \
  --set secretName=SECRET_NAME \
  --set serviceMonitor.enabled=true \
  --set serviceMonitor.namespace=NAMESPACE \
  --wait --timeout 5m

# Webhook Worker
helm upgrade --install HELM_RELEASE_WEBHOOK charts/webhook-worker \
  --namespace NAMESPACE \
  --set image.repository=REGISTRY/problemsolver-webhook-worker \
  --set image.tag=TAG \
  --set secretName=SECRET_NAME \
  --set serviceMonitor.enabled=true \
  --set serviceMonitor.namespace=NAMESPACE \
  --wait --timeout 5m

Notes:
- `--wait` causes Helm to wait for readiness. Readiness probes depend on DB connectivity.
- If a release fails, Helm will exit non-zero; check `kubectl describe pod` and logs.

---

## 4) Post-deploy validation (smoke tests)

### 4.1 Pods & readiness
kubectl get pods -n NAMESPACE -l app=problemsolver-poller
kubectl get pods -n NAMESPACE -l app=problemsolver-webhook

kubectl describe pod <pod> -n NAMESPACE
kubectl logs <pod> -n NAMESPACE -c poller

### 4.2 Service & metrics endpoint (inside cluster)
# Port-forward to local machine (if cluster network not accessible)
kubectl port-forward svc/problemsolver-poller-metrics 8002:8002 -n NAMESPACE &
curl -sS http://127.0.0.1:8002/metrics | head -n 40

kubectl port-forward svc/problemsolver-webhook-metrics 8001:8001 -n NAMESPACE &
curl -sS http://127.0.0.1:8001/metrics | head -n 40

Validate:
- Metrics endpoints return Prometheus metrics
- `problemsolver_poller_last_success_unixtime` present
- Counters exist: `problemsolver_deposits_processed_total`, `problemsolver_deposits_errors_total`, `problemsolver_collisions_total`

### 4.3 Prometheus & Grafana
- Confirm ServiceMonitors exist:
  kubectl get servicemonitor -n NAMESPACE

- In Prometheus UI (Targets), verify both metric endpoints are UP.

- Import or confirm Grafana dashboard (Problemsolver) shows metrics.

### 4.4 Functional smoke: invoice creation & simulated deposit
# Create an invoice (use API server; placeholder curl)
curl -X POST "https://api.example.com/api/invoices" \
  -H "Content-Type: application/json" \
  -d '{"merchant_id":"<MERCHANT_UUID>","base_amount":"10.00","network":"ERC20","address":"0x..."}'

- Verify invoice row exists in DB (publish_amount should be adjusted per amount-diff).
- Simulate deposit in staging:
  - Run E2E test harness or insert a deposit_raw matching the invoice and let the poller pick it up (preferred: use mocked Binance response in tests).
- Verify:
  - invoice.status == `paid`
  - a `payments` row exists
  - a `ledger_entries` row exists (append-only)
  - webhook_queue has an entry for the merchant
  - Grafana metrics increment accordingly

---

## 5) Monitoring & Alerts (ops)
- Alert on Poller failure: poller consecutive errors > 5 → P1 (PagerDuty)
- Alert on webhook failure rate > 5% over 10m → P2
- Alert on reconciliation mismatch rate > 0.1% → P1

---

## 6) Post-deploy housekeeping
- Rotate secrets if any temporary keys used.
- Document runbook incident owners in PagerDuty / Ops channel.
- Snapshot DB backup taken before first production funds processed.

---

## 7) Helpful commands
# Rollback Helm release (safe quick rollback)
helm rollback HELM_RELEASE_POLLER <REV> --namespace NAMESPACE
helm rollback HELM_RELEASE_WEBHOOK <REV> --namespace NAMESPACE

# Uninstall
helm uninstall HELM_RELEASE_POLLER --namespace NAMESPACE
helm uninstall HELM_RELEASE_WEBHOOK --namespace NAMESPACE

# Validate metrics via Prometheus query (example)
# rate(problemsolver_deposits_processed_total[5m])

---

## Notes for auditors
- All operational artifacts (Helm charts, ServiceMonitor templates, Grafana provisioning) are in the repository.
- Secrets are referenced but never committed.
- DB schema migrations are reversible and included (alembic/versions).
- Ledger is append-only via DB trigger; any attempt to UPDATE/DELETE ledger_entries will raise an exception.

If you need a one-click script that runs build → push → helm upgrade in CI, request "deliver CD script" and I will provide a secure, parameterized example.