#!/usr/bin/env bash
set -euo pipefail
# Local helper to run E2E tests in a dev environment
# Requires Docker & docker-compose or a running Postgres available at DATABASE_URL
# Example usage:
# DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5432/postgres ./scripts/run_e2e.sh

# Run alembic migrations then pytest E2E
export DATABASE_URL=${DATABASE_URL:-postgresql://postgres:postgres@127.0.0.1:5432/postgres}

echo "Running Alembic migrations..."
alembic upgrade head

echo "Running pytest e2e tests..."
pytest tests/e2e -q -k test_end_to_end_credit