"""
Sentry initialization helper. Read SENTRY_DSN from env via Settings.
"""
import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration
from app.core.config import settings

def init_sentry():
    dsn = getattr(settings, "SENTRY_DSN", None)
    if not dsn:
        return
    sentry_logging = LoggingIntegration(
        level=None,        # capture nothing by default from logging
        event_level="ERROR"  # send exceptions as errors
    )
    sentry_sdk.init(dsn, integrations=[sentry_logging], traces_sample_rate=0.0)