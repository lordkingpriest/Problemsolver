-- Postgres canonical DDL for Problemsolver (initial schema)
-- Note: requires superuser to CREATE EXTENSION pgcrypto (or ensure extension already present)
-- UUID generation uses gen_random_uuid() from pgcrypto.

-- 1) Extensions
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 2) merchants
CREATE TABLE IF NOT EXISTS merchants (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  risk_tier text NOT NULL DEFAULT 'low',
  onboarding_status text NOT NULL DEFAULT 'pending',
  created_at timestamptz NOT NULL DEFAULT now()
);

-- 3) api_keys
CREATE TABLE IF NOT EXISTS api_keys (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  merchant_id uuid NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  key_id text NOT NULL,               -- public identifier shown to merchant (masked)
  key_hash text NOT NULL,             -- hash of the secret token (do not store raw secret)
  created_at timestamptz NOT NULL DEFAULT now(),
  last_used_at timestamptz NULL
);
CREATE INDEX IF NOT EXISTS idx_api_keys_merchant ON api_keys(merchant_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_api_keys_key_id ON api_keys(key_id);

-- 4) invoices
CREATE TABLE IF NOT EXISTS invoices (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  merchant_id uuid NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  publish_amount numeric(36,18) NOT NULL,
  currency text NOT NULL DEFAULT 'USDT',
  network text NULL,
  address text NULL,
  address_tag text NULL,
  status text NOT NULL DEFAULT 'pending',
  publish_metadata jsonb NULL,
  expiry timestamptz NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_invoices_merchant ON invoices(merchant_id);
CREATE INDEX IF NOT EXISTS idx_invoices_address ON invoices(address);
CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status);

-- Unique constraint per spec: (merchant_id, publish_amount, address) when address present
CREATE UNIQUE INDEX IF NOT EXISTS ux_invoices_merchant_amount_address
ON invoices(merchant_id, publish_amount, address)
WHERE address IS NOT NULL;

-- 5) deposit_addresses
CREATE TABLE IF NOT EXISTS deposit_addresses (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  merchant_id uuid NULL REFERENCES merchants(id) ON DELETE SET NULL,
  invoice_id uuid NULL REFERENCES invoices(id) ON DELETE SET NULL,
  address text NOT NULL,
  network text NULL,
  allocated boolean NOT NULL DEFAULT false,
  metadata jsonb NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_deposit_addresses_address_network ON deposit_addresses(address, network);
CREATE INDEX IF NOT EXISTS idx_deposit_addresses_merchant ON deposit_addresses(merchant_id);

-- 6) poller_checkpoints
CREATE TABLE IF NOT EXISTS poller_checkpoints (
  key text PRIMARY KEY,           -- e.g., 'binance_deposit'
  last_insert_time_ms bigint NULL,
  last_tx_id text NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- 7) deposit_raw (raw Binance deposits persisted)
CREATE TABLE IF NOT EXISTS deposit_raw (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tx_id text NOT NULL,
  coin text NOT NULL,
  network text NULL,
  amount numeric(36,18) NOT NULL,
  status integer NOT NULL,
  address text NULL,
  address_tag text NULL,
  insert_time_ms bigint NOT NULL,
  complete_time_ms bigint NULL,
  raw jsonb NOT NULL,
  processed boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_deposit_raw_txid ON deposit_raw(tx_id);
CREATE INDEX IF NOT EXISTS idx_deposit_raw_address ON deposit_raw(address);
CREATE INDEX IF NOT EXISTS idx_deposit_raw_processed ON deposit_raw(processed);

-- 8) payments
CREATE TABLE IF NOT EXISTS payments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  invoice_id uuid NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
  deposit_raw_id uuid NULL REFERENCES deposit_raw(id) ON DELETE SET NULL,
  tx_id text NULL,
  amount numeric(36,18) NOT NULL,
  network text NULL,
  address text NULL,
  address_tag text NULL,
  status text NOT NULL DEFAULT 'settled', -- settled, pending, failed
  metadata jsonb NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
-- Unique constraint to avoid double-crediting: (tx_id, invoice_id)
CREATE UNIQUE INDEX IF NOT EXISTS ux_payments_txid_invoice ON payments(tx_id, invoice_id);

CREATE INDEX IF NOT EXISTS idx_payments_invoice ON payments(invoice_id);

-- 9) ledger_entries (append-only)
CREATE TABLE IF NOT EXISTS ledger_entries (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  merchant_id uuid NOT NULL REFERENCES merchants(id) ON DELETE CASCADE,
  change_amount numeric(36,18) NOT NULL, -- positive or negative
  currency text NOT NULL DEFAULT 'USDT',
  entry_type text NOT NULL, -- e.g., 'credit_invoice', 'fee', 'manual_adjustment'
  reference_id uuid NULL,   -- optional FK to payment or invoice or external settlement
  metadata jsonb NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ledger_merchant ON ledger_entries(merchant_id);
CREATE INDEX IF NOT EXISTS idx_ledger_created_at ON ledger_entries(created_at);

-- 10) webhook_queue
CREATE TABLE IF NOT EXISTS webhook_queue (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  merchant_id uuid NULL REFERENCES merchants(id) ON DELETE SET NULL,
  payload jsonb NOT NULL,
  headers jsonb NULL,
  attempts integer NOT NULL DEFAULT 0,
  last_error text NULL,
  status text NOT NULL DEFAULT 'pending', -- pending, in_progress, success, failed
  idempotency_key text NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  next_attempt_at timestamptz NULL
);
CREATE INDEX IF NOT EXISTS idx_webhook_queue_status ON webhook_queue(status);
CREATE INDEX IF NOT EXISTS idx_webhook_queue_merchant ON webhook_queue(merchant_id);

-- 11) audit_logs (append-only, keep long-term)
CREATE TABLE IF NOT EXISTS audit_logs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  actor text NULL,
  action text NOT NULL,
  details jsonb NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at);

-- 12) system_events
CREATE TABLE IF NOT EXISTS system_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source text NOT NULL,
  event_type text NOT NULL,
  payload jsonb NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_system_events_source ON system_events(source);

-- 13) Append-only enforcement for ledger_entries and audit_logs
-- Create a function to prevent UPDATE or DELETE on append-only tables
CREATE OR REPLACE FUNCTION prevent_update_delete() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'append-only table: updates/deletes are not allowed';
  RETURN NULL;
END;
$$;

-- Create triggers
CREATE TRIGGER trg_ledger_prevent_update_delete
BEFORE UPDATE OR DELETE ON ledger_entries
FOR EACH ROW EXECUTE FUNCTION prevent_update_delete();

CREATE TRIGGER trg_audit_prevent_update_delete
BEFORE UPDATE OR DELETE ON audit_logs
FOR EACH ROW EXECUTE FUNCTION prevent_update_delete();

-- 14) Additional recommended partial indexes (for collisions & idempotency monitoring)
-- Index to find invoices by (address, network, address_tag) quickly
CREATE INDEX IF NOT EXISTS idx_invoices_address_network_tag
ON invoices(address, network, address_tag);

-- End of schema.sql