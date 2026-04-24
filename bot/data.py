"""
Candle cache loader.
Reads from data/{SYMBOL}_{INTERVAL}.json written by scripts/fetch_history.py.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_candles(
    symbol: str,
    interval: str = "5m",
    last_n: Optional[int] = None,
) -> List[dict]:
    """
    Load cached klines for a symbol.
    Returns empty list if cache is missing — caller should run fetch_history.py.

    Args:
        symbol:   e.g. 'BTCUSDT'
        interval: e.g. '5m'
        last_n:   if set, return only the last N candles
    """
    path = DATA_DIR / f"{symbol}_{interval}.json"
    if not path.exists():
        return []
    with open(path) as f:
        candles: List[dict] = json.load(f)
    if last_n is not None:
        candles = candles[-last_n:]
    return candles


def candle_count(symbol: str, interval: str = "5m") -> int:
    """Return number of cached candles for a symbol, or 0 if missing."""
    return len(load_candles(symbol, interval))
