"""
Webhook worker: dequeues webhook_queue and delivers signed webhooks.

- Runs as separate container.
- Uses WEBHOOK_SECRET to sign payloads (X-PS-Timestamp + X-PS-Signature)
- Exponential backoff retry with next_attempt_at updates
- Emits Prometheus metrics: problemsolver_webhook_success_total, problemsolver_webhook_fail_total
"""
import asyncio
import logging
import time
from datetime import datetime, timezone, timedelta

import httpx
from prometheus_client import Counter, start_http_server

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.db.models import WebhookQueue
from app.utils.webhook_signing import sign_webhook

logger = logging.getLogger("problemsolver.webhooks.worker")

# Prometheus metrics
METRIC_WEBHOOK_SUCCESS = Counter("problemsolver_webhook_success_total", "Successful webhook deliveries")
METRIC_WEBHOOK_FAIL = Counter("problemsolver_webhook_fail_total", "Failed webhook deliveries")

# Config
WORKER_POLL_INTERVAL = int(getattr(settings, "WEBHOOK_WORKER_POLL_SECONDS", 2))
MAX_ATTEMPTS = int(getattr(settings, "WEBHOOK_MAX_ATTEMPTS", 10))
BACKOFF_BASE = int(getattr(settings, "WEBHOOK_BACKOFF_BASE_SECONDS", 1))


async def deliver_webhook(session, row):
    webhook_url = None
    # Expect merchant to store webhook URL in settings or merchant config; here we read from payload.headers if present
    headers = row.headers or {}
    webhook_url = headers.get("x-ps-webhook-url") or headers.get("webhook_url")
    if not webhook_url:
        logger.error("No webhook_url found for webhook_queue id=%s", row.id)
        return False, "no_webhook_url"

    payload_bytes = str(row.payload).encode("utf-8")
    timestamp = str(int(time.time()))
    signature = sign_webhook(payload_bytes, timestamp, settings.WEBHOOK_SECRET)
    req_headers = {
        "Content-Type": "application/json",
        "X-PS-Timestamp": timestamp,
        "X-PS-Signature": signature,
    }
    # Forward idempotency if present
    if row.idempotency_key:
        req_headers["Idempotency-Key"] = row.idempotency_key

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            r = await client.post(webhook_url, content=payload_bytes, headers=req_headers)
            if 200 <= r.status_code < 300:
                return True, None
            else:
                return False, f"status_{r.status_code}"
        except Exception as exc:
            return False, str(exc)


async def worker_loop():
    # Start Prometheus metrics endpoint on port 8001 by default
    metrics_port = int(getattr(settings, "WEBHOOK_METRICS_PORT", 8001))
    start_http_server(metrics_port)

    while True:
        async with AsyncSessionLocal() as db:
            # Fetch next pending and due webhook (next_attempt_at <= now or null)
            now = datetime.now(timezone.utc)
            stmt = (
                await db.execute(
                    """
                    SELECT id FROM webhook_queue
                    WHERE status = 'pending' AND (next_attempt_at IS NULL OR next_attempt_at <= now())
                    ORDER BY created_at ASC
                    LIMIT 1
                    """
                )
            )
            rowid = stmt.scalar_one_or_none()
            if not rowid:
                await asyncio.sleep(WORKER_POLL_INTERVAL)
                continue
            # Load the full row
            row = (await db.execute(select(WebhookQueue).where(WebhookQueue.id == rowid))).scalar_one()
            # Try delivery
            success, err = await deliver_webhook(db, row)
            if success:
                # mark success
                row.status = "success"
                row.attempts = (row.attempts or 0) + 1
                row.last_error = None
                await db.flush()
                METRIC_WEBHOOK_SUCCESS.inc()
                logger.info("Webhook delivered id=%s", row.id)
            else:
                # increment attempts and schedule retry
                attempts = (row.attempts or 0) + 1
                row.attempts = attempts
                row.last_error = err
                if attempts >= MAX_ATTEMPTS:
                    row.status = "failed"
                    logger.error("Webhook permanently failed id=%s attempts=%s error=%s", row.id, attempts, err)
                    METRIC_WEBHOOK_FAIL.inc()
                else:
                    backoff = min(600, BACKOFF_BASE * (2 ** (attempts - 1)))
                    row.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=backoff)
                    row.status = "pending"
                    logger.warning("Webhook delivery failed id=%s attempts=%s scheduled next in %s sec err=%s", row.id, attempts, backoff, err)
                    METRIC_WEBHOOK_FAIL.inc()
                await db.flush()
        await asyncio.sleep(0.1)  # slight throttle


def run_worker():
    # Basic runloop wrapper
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logger.info("Starting webhook worker")
    asyncio.run(worker_loop())


if __name__ == "__main__":
    run_worker()