# Rollback & Recovery Procedures — Problemsolver (Safe, Auditable)

This document lists safe rollback and recovery steps for Helm releases and the PostgreSQL database. Follow the safe path: prefer Helm rollback/uninstall in Kubernetes and DB restore from backup rather than downgrading schema in production.

IMPORTANT: Do not run DB schema downgrades on production unless you fully understand the migration implications and have an isolated recovery plan.

---

## 1) Quick rollback (Kubernetes / Helm) — preferred for app-level regressions

Use when new images or chart values cause runtime failures but DB schema is compatible with previous release.

1. Identify previous successful release revision:
   helm history HELM_RELEASE_POLLER --namespace NAMESPACE
   helm history HELM_RELEASE_WEBHOOK --namespace NAMESPACE

2. Rollback to the last known-good revision:
   helm rollback HELM_RELEASE_POLLER <REV> --namespace NAMESPACE
   helm rollback HELM_RELEASE_WEBHOOK <REV> --namespace NAMESPACE

3. Monitor pods:
   kubectl get pods -n NAMESPACE -l app=problemsolver-poller
   kubectl get pods -n NAMESPACE -l app=problemsolver-webhook

4. Verify:
   - Metrics endpoints UP
   - invoices/payments flow works on staging checks (see DEPLOYMENT.md smoke tests)

---

## 2) Uninstall and redeploy (if rollback not desirable)
1. Scale down / stop new release:
   helm uninstall HELM_RELEASE_POLLER --namespace NAMESPACE
   helm uninstall HELM_RELEASE_WEBHOOK --namespace NAMESPACE

2. Re-install previous charts with pinned image tags and validated values:
   helm upgrade --install HELM_RELEASE_POLLER charts/poller --namespace NAMESPACE --set image.tag=<previous-tag> --wait
   helm upgrade --install HELM_RELEASE_WEBHOOK charts/webhook-worker --namespace NAMESPACE --set image.tag=<previous-tag> --wait

3. Validate readiness and metrics.

---

## 3) Database issues & recovery (critical — handle with extreme caution)

Scenario A — Minor logical/data issue (no schema change)
- Stop Poller and related workers to prevent further ingestion:
  kubectl scale deployment HELM_RELEASE_POLLER --replicas=0 -n NAMESPACE
  kubectl scale deployment HELM_RELEASE_WEBHOOK --replicas=0 -n NAMESPACE
- Inspect problematic rows (deposit_raw, payments, ledger_entries)
- If safe, apply targeted SQL fixes via a controlled migration shell (not ad-hoc queries).
- Resume services (scale deployments back).

Scenario B — Corrupt schema change or catastrophic data issue
- DO NOT run Alembic downgrade in production unless approved by DB team and legal/compliance.
- Preferred safe recovery path:
  1. Restore DB from backup snapshot taken before migration.
  2. Point application staging/production to restored DB in a controlled environment.
  3. Reapply carefully validated migrations in staging; run full reconciliation tests.
  4. Promote rebuilt DB to production only after audit review.

Commands (example for RDS / managed PG with snapshot)
- Create new DB from snapshot using provider UI / CLI.
- Update a temporary staging release to point to the restored DB and run full reconciliation.

---

## 4) Emergency kill switch (operational)
If a security or integrity incident occurs (duplicate tx flood, Binance auth failure, massive reorg):

1. STOP poller & disable invoice creation:
   kubectl scale deployment HELM_RELEASE_POLLER --replicas=0 -n NAMESPACE
   # optionally block ingress to API that creates invoices (Ingress rule, or feature flag in app)

2. Notify on-call and ops per runbook (PagerDuty)
3. Create an incident ticket and gather evidence (logs, last_checkpoint, system_events)
4. Run reconciliations and manual resolution processes (see runbooks)

---

## 5) Verifying rollback success
- Post-rollback sanity checks:
  - `problemsolver_poller_last_success_unixtime` updated within expected timeframe
  - Deposit processing rate returns to baseline
  - No missing ledger entries for already-credited invoices
  - Audit logs created for manual interventions

---

## 6) Postmortem & audit
- For any rollback event that touches ledger/financial state, open a postmortem that includes:
  - Timeline and root cause
  - Affected merchant/invoice IDs
  - Data integrity proof (reconciled totals)
  - Remediation and policy changes
  - Legal/compliance notification if required

---

## 7) Quick references
- To stop poller quickly:
  kubectl scale deployment problemsolver-poller --replicas=0 -n NAMESPACE
- To re-run migrations in staging:
  alembic upgrade head
- To validate append-only enforcement:
  # Attempting to update ledger_entries should fail
  psql $DATABASE_URL -c "UPDATE ledger_entries SET change_amount = 0 WHERE id = '...';" # expected to raise

---

If you need, I will also produce:
- a pre-populated incident communication template (ops -> merchants/regulators),
- a runbook checklist for compromised Binance keys (rotate keys, re-sync ledger, notify exchanges),
- or automated rollback playbooks (Argo Rollouts / Flux-compatible).
```