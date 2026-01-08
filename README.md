```markdown
# Problemsolver Poller

This Poller is a separate process/container which is the only component allowed to call the Binance API.

What it does:
- Polls Binance deposit history (GET /sapi/v1/capital/deposit/hisrec)
- Uses server-time sync to correct timestamp skew
- Signs requests with HMAC-SHA256 using BINANCE_API_SECRET
- Idempotently stores raw deposits in `deposit_raw`
- Attempts conservative, atomic invoice matching & crediting
- Persists checkpoint in `poller_checkpoints` so it can resume after restart
- Emits webhook tasks by inserting into `webhook_queue` for the webhook worker to deliver

Running:
- Build the image: docker build -t problemsolver-poller -f poller/Dockerfile .
- Run with environment variables:
  - DATABASE_URL, BINANCE_API_KEY, BINANCE_API_SECRET, REDIS_URL (optional), POLLER_POLL_INTERVAL_SECONDS
- Example:
  docker run --env-file .env problemsolver-poller

Important:
- Do NOT commit secrets. Provide BINANCE_API_KEY and BINANCE_API_SECRET via K8s Secrets or a vault in production.
- Ensure the database has the poller tables (poller_checkpoints, deposit_raw, webhook_queue). Alembic migration scripts will be provided next.

Next work:
- Add robust amount-differentiation (k least significant digits reserved) per-network
- Add pooled-address vs unique-address allocation hooks
- Add webhook delivery worker and retry policy
- Add metrics (Prometheus) and observability
```