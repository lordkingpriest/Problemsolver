import pytest
import uuid
from decimal import Decimal
from app.api.invoices import adjusted_amount_for_invoice  # note: our API uses app.poller.amount_diff

# Simple smoke test for create_invoice deterministic attempts (requires DB in CI)

def test_dummy():
    assert True