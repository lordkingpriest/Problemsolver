"""Initial schema for Problemsolver

Revision ID: 0001_initial
Revises: 
Create Date: 2026-01-08 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # CREATE extension
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

    # merchants
    op.create_table(
        'merchants',
        sa.Column('id', sa.sql.sqltypes.UUID(), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('risk_tier', sa.Text(), nullable=False, server_default=sa.text("'low'")),
        sa.Column('onboarding_status', sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
    )

    # api_keys
    op.create_table(
        'api_keys',
        sa.Column('id', sa.sql.sqltypes.UUID(), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('merchant_id', sa.sql.sqltypes.UUID(), sa.ForeignKey('merchants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('key_id', sa.Text(), nullable=False),
        sa.Column('key_hash', sa.Text(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('last_used_at', sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index('idx_api_keys_merchant', 'api_keys', ['merchant_id'])
    op.create_index('ux_api_keys_key_id', 'api_keys', ['key_id'], unique=True)

    # invoices
    op.create_table(
        'invoices',
        sa.Column('id', sa.sql.sqltypes.UUID(), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('merchant_id', sa.sql.sqltypes.UUID(), sa.ForeignKey('merchants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('publish_amount', sa.Numeric(36, 18), nullable=False),
        sa.Column('currency', sa.Text(), nullable=False, server_default=sa.text("'USDT'")),
        sa.Column('network', sa.Text(), nullable=True),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('address_tag', sa.Text(), nullable=True),
        sa.Column('status', sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column('publish_metadata', sa.JSON(), nullable=True),
        sa.Column('expiry', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('idx_invoices_merchant', 'invoices', ['merchant_id'])
    op.create_index('idx_invoices_address', 'invoices', ['address'])
    op.create_index('idx_invoices_status', 'invoices', ['status'])
    # unique composite where address is not null
    op.create_index('ux_invoices_merchant_amount_address', 'invoices', ['merchant_id', 'publish_amount', 'address'], unique=True, postgresql_where=sa.text('address IS NOT NULL'))
    op.create_index('idx_invoices_address_network_tag', 'invoices', ['address', 'network', 'address_tag'])

    # deposit_addresses
    op.create_table(
        'deposit_addresses',
        sa.Column('id', sa.sql.sqltypes.UUID(), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('merchant_id', sa.sql.sqltypes.UUID(), sa.ForeignKey('merchants.id', ondelete='SET NULL'), nullable=True),
        sa.Column('invoice_id', sa.sql.sqltypes.UUID(), sa.ForeignKey('invoices.id', ondelete='SET NULL'), nullable=True),
        sa.Column('address', sa.Text(), nullable=False),
        sa.Column('network', sa.Text(), nullable=True),
        sa.Column('allocated', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ux_deposit_addresses_address_network', 'deposit_addresses', ['address', 'network'], unique=True)
    op.create_index('idx_deposit_addresses_merchant', 'deposit_addresses', ['merchant_id'])

    # poller_checkpoints
    op.create_table(
        'poller_checkpoints',
        sa.Column('key', sa.Text(), primary_key=True),
        sa.Column('last_insert_time_ms', sa.BigInteger(), nullable=True),
        sa.Column('last_tx_id', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
    )

    # deposit_raw
    op.create_table(
        'deposit_raw',
        sa.Column('id', sa.sql.sqltypes.UUID(), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tx_id', sa.Text(), nullable=False),
        sa.Column('coin', sa.Text(), nullable=False),
        sa.Column('network', sa.Text(), nullable=True),
        sa.Column('amount', sa.Numeric(36, 18), nullable=False),
        sa.Column('status', sa.Integer(), nullable=False),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('address_tag', sa.Text(), nullable=True),
        sa.Column('insert_time_ms', sa.BigInteger(), nullable=False),
        sa.Column('complete_time_ms', sa.BigInteger(), nullable=True),
        sa.Column('raw', sa.JSON(), nullable=False),
        sa.Column('processed', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ux_deposit_raw_txid', 'deposit_raw', ['tx_id'], unique=True)
    op.create_index('idx_deposit_raw_address', 'deposit_raw', ['address'])
    op.create_index('idx_deposit_raw_processed', 'deposit_raw', ['processed'])

    # payments
    op.create_table(
        'payments',
        sa.Column('id', sa.sql.sqltypes.UUID(), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('invoice_id', sa.sql.sqltypes.UUID(), sa.ForeignKey('invoices.id', ondelete='CASCADE'), nullable=False),
        sa.Column('deposit_raw_id', sa.sql.sqltypes.UUID(), sa.ForeignKey('deposit_raw.id', ondelete='SET NULL'), nullable=True),
        sa.Column('tx_id', sa.Text(), nullable=True),
        sa.Column('amount', sa.Numeric(36, 18), nullable=False),
        sa.Column('network', sa.Text(), nullable=True),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('address_tag', sa.Text(), nullable=True),
        sa.Column('status', sa.Text(), nullable=False, server_default=sa.text("'settled'")),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ux_payments_txid_invoice', 'payments', ['tx_id', 'invoice_id'], unique=True)
    op.create_index('idx_payments_invoice', 'payments', ['invoice_id'])

    # ledger_entries
    op.create_table(
        'ledger_entries',
        sa.Column('id', sa.sql.sqltypes.UUID(), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('merchant_id', sa.sql.sqltypes.UUID(), sa.ForeignKey('merchants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('change_amount', sa.Numeric(36, 18), nullable=False),
        sa.Column('currency', sa.Text(), nullable=False, server_default=sa.text("'USDT'")),
        sa.Column('entry_type', sa.Text(), nullable=False),
        sa.Column('reference_id', sa.sql.sqltypes.UUID(), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('idx_ledger_merchant', 'ledger_entries', ['merchant_id'])
    op.create_index('idx_ledger_created_at', 'ledger_entries', ['created_at'])

    # webhook_queue
    op.create_table(
        'webhook_queue',
        sa.Column('id', sa.sql.sqltypes.UUID(), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('merchant_id', sa.sql.sqltypes.UUID(), sa.ForeignKey('merchants.id', ondelete='SET NULL'), nullable=True),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('headers', sa.JSON(), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('status', sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column('idempotency_key', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('next_attempt_at', sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index('idx_webhook_queue_status', 'webhook_queue', ['status'])
    op.create_index('idx_webhook_queue_merchant', 'webhook_queue', ['merchant_id'])

    # audit_logs
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.sql.sqltypes.UUID(), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('actor', sa.Text(), nullable=True),
        sa.Column('action', sa.Text(), nullable=False),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('idx_audit_logs_created_at', 'audit_logs', ['created_at'])

    # system_events
    op.create_table(
        'system_events',
        sa.Column('id', sa.sql.sqltypes.UUID(), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('source', sa.Text(), nullable=False),
        sa.Column('event_type', sa.Text(), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('idx_system_events_source', 'system_events', ['source'])

    # Append-only trigger function
    op.execute("""
    CREATE OR REPLACE FUNCTION prevent_update_delete() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      RAISE EXCEPTION 'append-only table: updates/deletes are not allowed';
      RETURN NULL;
    END;
    $$;
    """)

    # Triggers for ledger_entries and audit_logs
    op.execute("CREATE TRIGGER trg_ledger_prevent_update_delete BEFORE UPDATE OR DELETE ON ledger_entries FOR EACH ROW EXECUTE FUNCTION prevent_update_delete();")
    op.execute("CREATE TRIGGER trg_audit_prevent_update_delete BEFORE UPDATE OR DELETE ON audit_logs FOR EACH ROW EXECUTE FUNCTION prevent_update_delete();")


def downgrade():
    # Drop triggers and function first
    op.execute("DROP TRIGGER IF EXISTS trg_ledger_prevent_update_delete ON ledger_entries;")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_prevent_update_delete ON audit_logs;")
    op.execute("DROP FUNCTION IF EXISTS prevent_update_delete();")

    # Drop tables in reverse order of creation
    op.drop_index('idx_system_events_source', table_name='system_events')
    op.drop_table('system_events')

    op.drop_index('idx_audit_logs_created_at', table_name='audit_logs')
    op.drop_table('audit_logs')

    op.drop_index('idx_webhook_queue_merchant', table_name='webhook_queue')
    op.drop_index('idx_webhook_queue_status', table_name='webhook_queue')
    op.drop_table('webhook_queue')

    op.drop_index('idx_ledger_created_at', table_name='ledger_entries')
    op.drop_index('idx_ledger_merchant', table_name='ledger_entries')
    op.drop_table('ledger_entries')

    op.drop_index('idx_payments_invoice', table_name='payments')
    op.drop_index('ux_payments_txid_invoice', table_name='payments')
    op.drop_table('payments')

    op.drop_index('idx_deposit_raw_processed', table_name='deposit_raw')
    op.drop_index('idx_deposit_raw_address', table_name='deposit_raw')
    op.drop_index('ux_deposit_raw_txid', table_name='deposit_raw')
    op.drop_table('deposit_raw')

    op.drop_table('poller_checkpoints')

    op.drop_index('idx_deposit_addresses_merchant', table_name='deposit_addresses')
    op.drop_index('ux_deposit_addresses_address_network', table_name='deposit_addresses')
    op.drop_table('deposit_addresses')

    op.drop_index('idx_invoices_address_network_tag', table_name='invoices')
    op.drop_index('ux_invoices_merchant_amount_address', table_name='invoices')
    op.drop_index('idx_invoices_status', table_name='invoices')
    op.drop_index('idx_invoices_address', table_name='invoices')
    op.drop_index('idx_invoices_merchant', table_name='invoices')
    op.drop_table('invoices')

    op.drop_index('ux_api_keys_key_id', table_name='api_keys')
    op.drop_index('idx_api_keys_merchant', table_name='api_keys')
    op.drop_table('api_keys')

    op.drop_table('merchants')

    # Optionally drop extension - leave to DBA. If you want to drop, uncomment:
    # op.execute("DROP EXTENSION IF EXISTS pgcrypto;")