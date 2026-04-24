"""
Thin signed HTTP client for Binance Spot API v3.
Authentication: HMAC-SHA256 (System-generated key).
Docs: https://developers.binance.com/docs/binance-spot-api-docs/rest-api
"""
from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import requests

from bot import config

_SESSION = requests.Session()
_SESSION.headers.update({"X-MBX-APIKEY": config.API_KEY})


# ---------------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------------

def _sign(params: Dict[str, Any]) -> str:
    """Return HMAC-SHA256 hex signature of URL-encoded params."""
    query = urlencode(params)
    return hmac.new(
        config.API_SECRET.encode("utf-8"),
        query.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _timestamp() -> int:
    return int(time.time() * 1000)


# ---------------------------------------------------------------------------
# Public (unsigned) endpoints
# ---------------------------------------------------------------------------

def get_server_time() -> int:
    """Returns Binance server time in ms. Used for clock-skew check."""
    resp = _SESSION.get(f"{config.BASE_URL}/api/v3/time", timeout=10)
    resp.raise_for_status()
    return resp.json()["serverTime"]


def get_klines(symbol: str, interval: str = "5m", limit: int = 150) -> list:
    """
    Fetch candlestick data.
    Returns list of dicts with keys: open_time, open, high, low, close, volume, close_time.
    Raw Binance kline array indices:
      0 open_time, 1 open, 2 high, 3 low, 4 close, 5 volume, 6 close_time
    """
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    resp = _SESSION.get(f"{config.BASE_URL}/api/v3/klines", params=params, timeout=10)
    resp.raise_for_status()
    raw = resp.json()
    return [
        {
            "open_time": c[0],
            "open": float(c[1]),
            "high": float(c[2]),
            "low": float(c[3]),
            "close": float(c[4]),
            "volume": float(c[5]),
            "close_time": c[6],
        }
        for c in raw
    ]


def get_orderbook_ticker(symbol: str) -> Dict[str, float]:
    """Returns best bid/ask for spread check."""
    resp = _SESSION.get(
        f"{config.BASE_URL}/api/v3/ticker/bookTicker",
        params={"symbol": symbol},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    return {
        "bid": float(data["bidPrice"]),
        "ask": float(data["askPrice"]),
    }


def get_exchange_info(symbol: str) -> Dict[str, Any]:
    """Fetch symbol filters (LOT_SIZE, NOTIONAL, PRICE_FILTER etc.)."""
    resp = _SESSION.get(
        f"{config.BASE_URL}/api/v3/exchangeInfo",
        params={"symbol": symbol},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Private (signed) endpoints — require API_KEY + API_SECRET
# ---------------------------------------------------------------------------

def get_account() -> Dict[str, Any]:
    """Returns account info including balances."""
    params: Dict[str, Any] = {"timestamp": _timestamp(), "recvWindow": 5000}
    params["signature"] = _sign(params)
    resp = _SESSION.get(f"{config.BASE_URL}/api/v3/account", params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_open_orders(symbol: str) -> list:
    """Returns list of open orders for a symbol."""
    params: Dict[str, Any] = {
        "symbol": symbol,
        "timestamp": _timestamp(),
        "recvWindow": 5000,
    }
    params["signature"] = _sign(params)
    resp = _SESSION.get(f"{config.BASE_URL}/api/v3/openOrders", params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_my_trades(symbol: str, start_time_ms: int) -> list:
    """Returns trades since start_time_ms (for daily PnL calculation)."""
    params: Dict[str, Any] = {
        "symbol": symbol,
        "startTime": start_time_ms,
        "timestamp": _timestamp(),
        "recvWindow": 5000,
    }
    params["signature"] = _sign(params)
    resp = _SESSION.get(f"{config.BASE_URL}/api/v3/myTrades", params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def place_limit_order(
    symbol: str,
    side: str,
    quantity: float,
    price: float,
    time_in_force: str = "GTC",
    dry_run: bool = True,
) -> Dict[str, Any]:
    """
    Place a LIMIT order (or simulate if dry_run=True).
    side: 'BUY' or 'SELL'
    """
    if dry_run:
        return {
            "orderId": -1,
            "symbol": symbol,
            "side": side,
            "type": "LIMIT",
            "price": price,
            "origQty": quantity,
            "status": "DRY_RUN",
        }
    params: Dict[str, Any] = {
        "symbol": symbol,
        "side": side,
        "type": "LIMIT",
        "timeInForce": time_in_force,
        "quantity": f"{quantity:.8f}",
        "price": f"{price:.8f}",
        "timestamp": _timestamp(),
        "recvWindow": 5000,
    }
    params["signature"] = _sign(params)
    resp = _SESSION.post(f"{config.BASE_URL}/api/v3/order", params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def cancel_order(symbol: str, order_id: int, dry_run: bool = True) -> Dict[str, Any]:
    """Cancel an open order by orderId."""
    if dry_run:
        return {"orderId": order_id, "status": "DRY_RUN_CANCELLED"}
    params: Dict[str, Any] = {
        "symbol": symbol,
        "orderId": order_id,
        "timestamp": _timestamp(),
        "recvWindow": 5000,
    }
    params["signature"] = _sign(params)
    resp = _SESSION.delete(f"{config.BASE_URL}/api/v3/order", params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_usdt_balance() -> float:
    """Convenience: return free USDT balance."""
    account = get_account()
    for asset in account.get("balances", []):
        if asset["asset"] == "USDT":
            return float(asset["free"])
    return 0.0


# ---------------------------------------------------------------------------
# Historical klines (paginated, public — no auth)
# ---------------------------------------------------------------------------

MAX_KLINES_PER_REQUEST = 1000
_5M_MS = 5 * 60 * 1000  # 5 minutes in milliseconds


def get_klines_range(
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int,
) -> list:
    """
    Fetch all klines between start_ms and end_ms by paginating
    through Binance's 1000-candle-per-request limit.
    Returns list of candle dicts (same format as get_klines).
    """
    all_candles = []
    current_start = start_ms

    while current_start < end_ms:
        params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": current_start,
            "endTime": end_ms,
            "limit": MAX_KLINES_PER_REQUEST,
        }
        resp = _SESSION.get(
            f"{config.BASE_URL}/api/v3/klines", params=params, timeout=15
        )
        resp.raise_for_status()
        raw = resp.json()
        if not raw:
            break

        candles = [
            {
                "open_time": c[0],
                "open": float(c[1]),
                "high": float(c[2]),
                "low": float(c[3]),
                "close": float(c[4]),
                "volume": float(c[5]),
                "close_time": c[6],
            }
            for c in raw
        ]
        all_candles.extend(candles)

        # Advance past the last returned candle
        last_close_time = raw[-1][6]
        current_start = last_close_time + 1

        # Stop if we got fewer than the max (means we've reached the end)
        if len(raw) < MAX_KLINES_PER_REQUEST:
            break

    # Deduplicate by open_time (safety guard against off-by-one overlaps)
    seen: set = set()
    unique = []
    for c in all_candles:
        if c["open_time"] not in seen:
            seen.add(c["open_time"])
            unique.append(c)

    return unique
