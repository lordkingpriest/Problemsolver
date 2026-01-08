````markdown
# Problemsolver - FastAPI backend (skeleton)

This repository contains the FastAPI backend skeleton for Problemsolver (crypto payment gateway MVP).

Highlights:
- FastAPI service with /api/health (always 200) and /api/ready (checks DB & Redis)
- Binance signing helper (HMAC SHA256)
- Webhook signing & verification helper
- Async SQLAlchemy session and minimal models
- No secrets in code — configure via environment variables or secret manager

Next steps:
1. Implement full models for ledger_entries, payments, deposit_addresses, api_keys, audit_logs.
2. Add Alembic migrations and migration scripts.
3. Implement poller service (separate container) to call Binance /sapi/v1/capital/deposit/hisrec.
4. Add background workers, metrics (Prometheus), and Sentry integration.
5. Implement thorough unit & integration tests.

Run:
- Populate environment variables (DATABASE_URL, REDIS_URL,...)
- Start with `uvicorn app.main:app --reload --port 8000`
