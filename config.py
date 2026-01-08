"""
Poller configuration & network confirmation defaults.
"""
from app.core.config import settings

# Default confirmation requirements per network (can be overridden via env/config)
# Spec: Default required confirmations = 2 (configurable), recommended staging defaults: ERC20=12, BEP20=3, TRC20=20
DEFAULT_NETWORK_CONFIRMATIONS = {
    "ETH": 12,    # ERC20 USDT - token name or network field mapping may vary
    "ERC20": 12,
    "BEP20": 3,
    "TRC20": 20,
    "TRON": 20,
}

# Default fallback confirmations if network unknown
FALLBACK_REQUIRED_CONFIRMATIONS = int(getattr(settings, "DEFAULT_CONFIRMATIONS", 2))

def required_confirmations_for(network: str | None) -> int:
    if not network:
        return FALLBACK_REQUIRED_CONFIRMATIONS
    key = network.upper()
    return DEFAULT_NETWORK_CONFIRMATIONS.get(key, FALLBACK_REQUIRED_CONFIRMATIONS)