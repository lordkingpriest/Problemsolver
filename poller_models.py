"""
Additional DB models used by the Poller service.

These models will require Alembic migrations (included later as requested).
We keep them separate from the main models file to reduce merge friction in the skeleton.
"""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base
import uuid
from sqlalchemy.sql import func

from app.db.models import Base  # reuse existing Base

class PollerCheckpoint(Base):
    __tablename__ = "poller_checkpoints"
    # single-row per poller name (key), allows multiple pollers (binance_deposit, reconciliation, ...)
    key = sa.Column(sa.String(128), primary_key=True)
    # last processed insertTime (ms since epoch) returned by Binance
    last_insert_time_ms = sa.Column(sa.BigInteger, nullable=True)
    # last processed txId for additional safety
    last_tx_id = sa.Column(sa.String(255), nullable=True)
    updated_at = sa.Column(sa.DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {"key": self.key, "last_insert_time_ms": self.last_insert_time_ms, "last_tx_id": self.last_tx_id}


class DepositRaw(Base):
    __tablename__ = "deposit_raw"
    id = sa.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tx_id = sa.Column(sa.String(255), nullable=False, unique=True, index=True)
    coin = sa.Column(sa.String(32), nullable=False)
    network = sa.Column(sa.String(32), nullable=True)
    amount = sa.Column(sa.Numeric(36, 18), nullable=False)
    status = sa.Column(sa.Integer, nullable=False)
    address = sa.Column(sa.String(255), nullable=True, index=True)
    address_tag = sa.Column(sa.String(255), nullable=True, index=True)
    insert_time_ms = sa.Column(sa.BigInteger, nullable=False)
    complete_time_ms = sa.Column(sa.BigInteger, nullable=True)
    raw = sa.Column(sa.JSON, nullable=False)
    processed = sa.Column(sa.Boolean, server_default=sa.text("false"), nullable=False, index=True)
    created_at = sa.Column(sa.DateTime(timezone=True), server_default=func.now())


class WebhookQueue(Base):
    __tablename__ = "webhook_queue"
    id = sa.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id = sa.Column(UUID(as_uuid=True), nullable=True, index=True)
    payload = sa.Column(sa.JSON, nullable=False)
    headers = sa.Column(sa.JSON, nullable=True)
    attempts = sa.Column(sa.Integer, nullable=False, server_default="0")
    last_error = sa.Column(sa.Text, nullable=True)
    status = sa.Column(sa.String(32), nullable=False, server_default="pending", index=True)
    created_at = sa.Column(sa.DateTime(timezone=True), server_default=func.now())