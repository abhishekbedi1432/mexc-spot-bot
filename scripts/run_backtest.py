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
import sys
from pathlib import Path

# Ensure project root is on path when run as script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot import config
from bot.backtester import run_backtest, BacktestMetrics
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
    print("Phase 0: kline fetching not yet wired. Results will be empty.\n")

    results = []
    for symbol in symbols:
        for strategy in strategies:
            # Phase 2: replace [] with fetched klines
            candles = []
            metrics = run_backtest(strategy, candles, symbol=symbol)
            results.append(metrics.summary())
            print(metrics.summary())

    return 0


if __name__ == "__main__":
    sys.exit(main())
