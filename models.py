"""
Async SQLAlchemy models matching the canonical DDL exactly.
No ORM-side business logic. DB is the source-of-truth.
"""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func
import uuid

Base = declarative_base()

# merchants
class Merchant(Base):
    __tablename__ = "merchants"
    id = sa.Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    name = sa.Column(sa.Text(), nullable=False)
    risk_tier = sa.Column(sa.Text(), nullable=False, server_default=sa.text("'low'"))
    onboarding_status = sa.Column(sa.Text(), nullable=False, server_default=sa.text("'pending'"))
    created_at = sa.Column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()"))

# api_keys
class APIKey(Base):
    __tablename__ = "api_keys"
    id = sa.Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    merchant_id = sa.Column(UUID(as_uuid=True), sa.ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False)
    key_id = sa.Column(sa.Text(), nullable=False)
    key_hash = sa.Column(sa.Text(), nullable=False)
    created_at = sa.Column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()"))
    last_used_at = sa.Column(sa.TIMESTAMP(timezone=True), nullable=True)

# invoices
class Invoice(Base):
    __tablename__ = "invoices"
    id = sa.Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    merchant_id = sa.Column(UUID(as_uuid=True), sa.ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False)
    publish_amount = sa.Column(sa.Numeric(36, 18), nullable=False)
    currency = sa.Column(sa.Text(), nullable=False, server_default=sa.text("'USDT'"))
    network = sa.Column(sa.Text(), nullable=True)
    address = sa.Column(sa.Text(), nullable=True)
    address_tag = sa.Column(sa.Text(), nullable=True)
    status = sa.Column(sa.Text(), nullable=False, server_default=sa.text("'pending'"))
    publish_metadata = sa.Column(sa.JSON(), nullable=True)
    expiry = sa.Column(sa.TIMESTAMP(timezone=True), nullable=True)
    created_at = sa.Column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()"))

    __table_args__ = (
        sa.Index("idx_invoices_merchant", "merchant_id"),
        sa.Index("idx_invoices_address", "address"),
        sa.Index("idx_invoices_status", "status"),
        sa.Index("idx_invoices_address_network_tag", "address", "network", "address_tag"),
        sa.Index("ux_invoices_merchant_amount_address", "merchant_id", "publish_amount", "address",
                 unique=True, postgresql_where=sa.text("address IS NOT NULL")),
    )

# deposit_addresses
class DepositAddress(Base):
    __tablename__ = "deposit_addresses"
    id = sa.Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    merchant_id = sa.Column(UUID(as_uuid=True), sa.ForeignKey("merchants.id", ondelete="SET NULL"), nullable=True)
    invoice_id = sa.Column(UUID(as_uuid=True), sa.ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True)
    address = sa.Column(sa.Text(), nullable=False)
    network = sa.Column(sa.Text(), nullable=True)
    allocated = sa.Column(sa.Boolean(), nullable=False, server_default=sa.text("false"))
    metadata = sa.Column(sa.JSON(), nullable=True)
    created_at = sa.Column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()"))

    __table_args__ = (
        sa.Index("ux_deposit_addresses_address_network", "address", "network", unique=True),
        sa.Index("idx_deposit_addresses_merchant", "merchant_id"),
    )

# poller_checkpoints
class PollerCheckpoint(Base):
    __tablename__ = "poller_checkpoints"
    key = sa.Column(sa.Text(), primary_key=True)
    last_insert_time_ms = sa.Column(sa.BigInteger(), nullable=True)
    last_tx_id = sa.Column(sa.Text(), nullable=True)
    updated_at = sa.Column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()"))

# deposit_raw
class DepositRaw(Base):
    __tablename__ = "deposit_raw"
    id = sa.Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    tx_id = sa.Column(sa.Text(), nullable=False)
    coin = sa.Column(sa.Text(), nullable=False)
    network = sa.Column(sa.Text(), nullable=True)
    amount = sa.Column(sa.Numeric(36, 18), nullable=False)
    status = sa.Column(sa.Integer(), nullable=False)
    address = sa.Column(sa.Text(), nullable=True)
    address_tag = sa.Column(sa.Text(), nullable=True)
    insert_time_ms = sa.Column(sa.BigInteger(), nullable=False)
    complete_time_ms = sa.Column(sa.BigInteger(), nullable=True)
    raw = sa.Column(sa.JSON(), nullable=False)
    processed = sa.Column(sa.Boolean(), nullable=False, server_default=sa.text("false"))
    created_at = sa.Column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()"))

    __table_args__ = (
        sa.Index("ux_deposit_raw_txid", "tx_id", unique=True),
        sa.Index("idx_deposit_raw_address", "address"),
        sa.Index("idx_deposit_raw_processed", "processed"),
    )

# payments
class Payment(Base):
    __tablename__ = "payments"
    id = sa.Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    invoice_id = sa.Column(UUID(as_uuid=True), sa.ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False)
    deposit_raw_id = sa.Column(UUID(as_uuid=True), sa.ForeignKey("deposit_raw.id", ondelete="SET NULL"), nullable=True)
    tx_id = sa.Column(sa.Text(), nullable=True)
    amount = sa.Column(sa.Numeric(36, 18), nullable=False)
    network = sa.Column(sa.Text(), nullable=True)
    address = sa.Column(sa.Text(), nullable=True)
    address_tag = sa.Column(sa.Text(), nullable=True)
    status = sa.Column(sa.Text(), nullable=False, server_default=sa.text("'settled'"))
    metadata = sa.Column(sa.JSON(), nullable=True)
    created_at = sa.Column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()"))

    __table_args__ = (
        sa.Index("ux_payments_txid_invoice", "tx_id", "invoice_id", unique=True),
        sa.Index("idx_payments_invoice", "invoice_id"),
    )

# ledger_entries (append-only)
class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    id = sa.Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    merchant_id = sa.Column(UUID(as_uuid=True), sa.ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False)
    change_amount = sa.Column(sa.Numeric(36, 18), nullable=False)
    currency = sa.Column(sa.Text(), nullable=False, server_default=sa.text("'USDT'"))
    entry_type = sa.Column(sa.Text(), nullable=False)
    reference_id = sa.Column(UUID(as_uuid=True), nullable=True)
    metadata = sa.Column(sa.JSON(), nullable=True)
    created_at = sa.Column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()"))

    __table_args__ = (
        sa.Index("idx_ledger_merchant", "merchant_id"),
        sa.Index("idx_ledger_created_at", "created_at"),
    )

# webhook_queue
class WebhookQueue(Base):
    __tablename__ = "webhook_queue"
    id = sa.Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    merchant_id = sa.Column(UUID(as_uuid=True), sa.ForeignKey("merchants.id", ondelete="SET NULL"), nullable=True)
    payload = sa.Column(sa.JSON(), nullable=False)
    headers = sa.Column(sa.JSON(), nullable=True)
    attempts = sa.Column(sa.Integer(), nullable=False, server_default=sa.text("0"))
    last_error = sa.Column(sa.Text(), nullable=True)
    status = sa.Column(sa.Text(), nullable=False, server_default=sa.text("'pending'"))
    idempotency_key = sa.Column(sa.Text(), nullable=True)
    created_at = sa.Column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()"))
    next_attempt_at = sa.Column(sa.TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        sa.Index("idx_webhook_queue_status", "status"),
        sa.Index("idx_webhook_queue_merchant", "merchant_id"),
    )

# audit_logs (append-only)
class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = sa.Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    actor = sa.Column(sa.Text(), nullable=True)
    action = sa.Column(sa.Text(), nullable=False)
    details = sa.Column(sa.JSON(), nullable=True)
    created_at = sa.Column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()"))

    __table_args__ = (
        sa.Index("idx_audit_logs_created_at", "created_at"),
    )

# system_events
class SystemEvent(Base):
    __tablename__ = "system_events"
    id = sa.Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    source = sa.Column(sa.Text(), nullable=False)
    event_type = sa.Column(sa.Text(), nullable=False)
    payload = sa.Column(sa.JSON(), nullable=True)
    created_at = sa.Column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()"))

    __table_args__ = (
        sa.Index("idx_system_events_source", "source"),
    )