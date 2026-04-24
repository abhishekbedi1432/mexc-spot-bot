#!/usr/bin/env python3
"""
Run backtests for all strategies × all pairs.
Phase 2: Full implementation (fetches 30 days of 5-min klines).
Phase 0: Scaffold — prints placeholder.

Usage:
  python scripts/run_backtest.py
  python scripts/run_backtest.py --symbol BTCUSDT --strategy mean_reversion
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure project root is on path when run as script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot import config
from bot.backtester import run_backtest, BacktestMetrics

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_candles(symbol: str, interval: str = "5m") -> list:
    """Load cached klines. Returns [] if cache missing (run fetch_history.py first)."""
    path = DATA_DIR / f"{symbol}_{interval}.json"
    if not path.exists():
        print(f"  [{symbol}] No cache found at {path}. Run: python scripts/fetch_history.py")
        return []
    with open(path) as f:
        return json.load(f)
from bot.strategies.mean_reversion import MeanReversionStrategy
from bot.strategies.trend_ema import TrendEMAStrategy
from bot.strategies.breakout_donchian import BreakoutDonchianStrategy
from bot.strategies.momentum_macd import MomentumMACDStrategy

STRATEGIES = [
    MeanReversionStrategy(),
    TrendEMAStrategy(),
    BreakoutDonchianStrategy(),
    MomentumMACDStrategy(),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run backtests")
    parser.add_argument("--symbol", default=None, help="Single symbol to test (default: all)")
    parser.add_argument("--strategy", default=None, help="Single strategy name (default: all)")
    parser.add_argument("--days", type=int, default=30, help="Lookback days (default: 30)")
    args = parser.parse_args()

    symbols = [args.symbol] if args.symbol else config.PAIRS
    strategies = [s for s in STRATEGIES if args.strategy is None or s.name == args.strategy]

    print(f"Backtest: {len(symbols)} pair(s) × {len(strategies)} strategy(ies) | {args.days} days")
    print("Loading klines from data/ cache (run fetch_history.py if cache is missing)\n")

    results = []
    for symbol in symbols:
        candles = load_candles(symbol)
        if not candles:
            continue
        print(f"  [{symbol}] {len(candles):,} candles loaded")
        for strategy in strategies:
            metrics = run_backtest(strategy, candles, symbol=symbol)
            results.append(metrics.summary())
            print(f"    {strategy.name:<25} {metrics.summary()}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
