#!/usr/bin/env python3
"""
Fetch and cache 30 days of 5-min klines per pair from Binance public API.
No API key required — public endpoint.

Usage:
  python scripts/fetch_history.py              # all pairs, 30 days
  python scripts/fetch_history.py --days 7     # last 7 days
  python scripts/fetch_history.py --symbol BTCUSDT
  python scripts/fetch_history.py --force      # ignore cache, re-fetch

Output:  data/{SYMBOL}_5m.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot import config
from bot.binance_client import get_klines_range

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CACHE_MAX_AGE_HOURS = 6


def cache_path(symbol: str, interval: str) -> Path:
    return DATA_DIR / f"{symbol}_{interval}.json"


def is_cache_fresh(path: Path) -> bool:
    if not path.exists():
        return False
    mtime = path.stat().st_mtime
    age_hours = (time.time() - mtime) / 3600
    return age_hours < CACHE_MAX_AGE_HOURS


def fetch_and_save(symbol: str, interval: str, days: int, force: bool = False) -> list:
    path = cache_path(symbol, interval)

    if not force and is_cache_fresh(path):
        print(f"  [{symbol}] Cache is fresh (< {CACHE_MAX_AGE_HOURS}h). Loading from disk.")
        with open(path) as f:
            candles = json.load(f)
        print(f"  [{symbol}] Loaded {len(candles):,} candles from cache.")
        return candles

    now_ms = int(time.time() * 1000)
    start_ms = now_ms - days * 24 * 60 * 60 * 1000

    start_str = datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
    print(f"  [{symbol}] Fetching {days}d of {interval} klines from {start_str} UTC ...")

    candles = get_klines_range(symbol, interval, start_ms, now_ms)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(candles, f)

    print(f"  [{symbol}] ✓ {len(candles):,} candles saved → {path.name}")
    return candles


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch historical klines from Binance")
    parser.add_argument("--symbol", default=None, help="Single symbol (default: all pairs)")
    parser.add_argument("--days", type=int, default=30, help="Days of history (default: 30)")
    parser.add_argument("--interval", default="5m", help="Kline interval (default: 5m)")
    parser.add_argument("--force", action="store_true", help="Force re-fetch even if cache is fresh")
    args = parser.parse_args()

    symbols = [args.symbol] if args.symbol else config.PAIRS
    expected_candles = args.days * 24 * 60 // 5  # approximate

    print(f"\nFetching {args.days}d × {args.interval} klines for: {symbols}")
    print(f"Expected ~{expected_candles:,} candles per symbol\n")

    results = {}
    errors = []
    for symbol in symbols:
        try:
            candles = fetch_and_save(symbol, args.interval, args.days, args.force)
            results[symbol] = len(candles)
        except Exception as exc:
            print(f"  [{symbol}] ERROR: {exc}")
            errors.append(symbol)

    print("\n── Summary ──────────────────────────────")
    for symbol, count in results.items():
        coverage = count / expected_candles * 100
        status = "✓" if coverage > 95 else "⚠ low"
        print(f"  {symbol:<12} {count:>6,} candles  ({coverage:.1f}% of expected)  {status}")

    if errors:
        print(f"\n  FAILED: {errors}")
        return 1

    print(f"\nCache directory: {DATA_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
