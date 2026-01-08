import hmac
import hashlib


def sign_binance_query(query_string: str, api_secret: str) -> str:
    """
    Return hex-encoded HMAC SHA256 signature for Binance private endpoints.
    Binance expects signature = HMAC_SHA256(secret, query_string)
    (Do NOT include 'signature=' in the value returned; caller should append as needed.)
    """
    if api_secret is None:
        raise ValueError("api_secret required for signing")
    mac = hmac.new(api_secret.encode("utf-8"), query_string.encode("utf-8"), hashlib.sha256)
    return mac.hexdigest()