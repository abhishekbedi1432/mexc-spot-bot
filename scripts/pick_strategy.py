#!/usr/bin/env python3
"""
Pick the best strategy per pair based on backtest metrics.
Writes result to config/chosen_strategies.json.
Phase 2: Full implementation.
Phase 0: Scaffold.

Usage:
  python scripts/pick_strategy.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot import config
from bot.backtester import run_backtest
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

SCORE_WEIGHTS = {
    "net_pnl_usdt": 0.4,
    "profit_factor": 0.3,
    "win_rate": 0.2,
    # max_drawdown penalises — lower is better
    "max_drawdown_pct": -0.1,
}


def score(metrics_summary: dict) -> float:
    """Composite score for ranking strategies."""
    s = 0.0
    for key, weight in SCORE_WEIGHTS.items():
        s += metrics_summary.get(key, 0.0) * weight
    return s


def main() -> int:
    print("Phase 0: no kline data available yet. Defaulting all pairs → mean_reversion.\n")

    # Phase 2+: fetch klines and run real backtest per pair × strategy
    chosen = {}
    for symbol in config.PAIRS:
        best_name = "mean_reversion"  # default until backtest runs
        best_score = float("-inf")
        for strategy in STRATEGIES:
            candles: list = []  # Phase 2: fetch real klines
            metrics = run_backtest(strategy, candles, symbol=symbol)
            s = score(metrics.summary())
            if s > best_score:
                best_score = s
                best_name = strategy.name
        chosen[symbol] = best_name
        print(f"  {symbol}: {best_name} (score={best_score:.4f})")

    config.save_chosen_strategies(chosen)
    print(f"\nSaved to {config.CHOSEN_STRATEGIES_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
