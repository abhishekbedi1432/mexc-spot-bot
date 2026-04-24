#!/usr/bin/env python3
"""
Cross-interval optimizer.
Tests all combinations of interval × strategy × pair and ranks by aggregate PnL.
Uses current optimized params: SL=1.25, TP=1.5, min_confidence=0.3, profit_gate=3×.

Why intervals matter:
  5m  ATR ≈ 0.3% of price → TP ≈ 0.45% gross  (2.25× fees — marginal)
  15m ATR ≈ 0.7% of price → TP ≈ 1.05% gross  (5.25× fees — viable)
  30m ATR ≈ 1.0% of price → TP ≈ 1.50% gross  (7.5× fees  — good)
  1h  ATR ≈ 1.5% of price → TP ≈ 2.25% gross  (11.25× fees — strong)

Trade-off: higher TF = better edge per trade, but fewer signals (less statistical power).

Usage:
  python scripts/optimize_intervals.py
  python scripts/optimize_intervals.py --symbol ETHUSDT
  python scripts/optimize_intervals.py --intervals 15m 30m 1h
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot import config
from bot.backtester import BacktestMetrics, run_backtest
from bot.data import load_candles
from bot.strategies.mean_reversion import MeanReversionStrategy
from bot.strategies.trend_ema import TrendEMAStrategy
from bot.strategies.breakout_donchian import BreakoutDonchianStrategy
from bot.strategies.momentum_macd import MomentumMACDStrategy

INTERVALS = ["5m", "15m", "30m", "1h"]
MIN_CONFIDENCE = 0.3

STRATEGIES = [
    MeanReversionStrategy(),
    TrendEMAStrategy(),
    BreakoutDonchianStrategy(),
    MomentumMACDStrategy(),
]

# Minimum trades to consider a result meaningful
MIN_TRADES_THRESHOLD = 3


def _agg_stats(metrics_list: list[BacktestMetrics]) -> dict:
    n = len(metrics_list)
    total_pnl = sum(m.net_pnl_usdt for m in metrics_list)
    total_trades = sum(m.total_trades for m in metrics_list)
    positive = sum(1 for m in metrics_list if m.net_pnl_usdt > 0)
    meaningful = sum(1 for m in metrics_list if m.total_trades >= MIN_TRADES_THRESHOLD)
    win_traded = sum(m.winning_trades for m in metrics_list)
    all_trades = total_trades
    avg_win_rate = win_traded / all_trades if all_trades > 0 else 0.0
    return {
        "total_pnl": total_pnl,
        "total_trades": total_trades,
        "avg_win_rate": avg_win_rate,
        "positive_combos": positive,
        "meaningful_combos": meaningful,
        "combos": n,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Cross-interval strategy optimizer")
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--intervals", nargs="+", default=INTERVALS,
                        choices=["5m", "15m", "30m", "1h"],
                        help="Intervals to test (default: all)")
    args = parser.parse_args()

    symbols = [args.symbol] if args.symbol else config.PAIRS

    print(f"\nInterval optimizer: {args.intervals} × {len(STRATEGIES)} strategies × {len(symbols)} pairs")
    print(f"min_confidence={MIN_CONFIDENCE}  SL={config.SL_ATR_MULT}  TP={config.TP_ATR_MULT}  "
          f"profit_gate={config.MIN_PROFIT_FEE_MULTIPLE}×\n")

    # interval → {strategy → {symbol → metrics}}
    all_results: dict[str, dict] = {}

    for interval in args.intervals:
        all_results[interval] = {}
        candles_map = {s: load_candles(s, interval) for s in symbols}
        missing = [s for s, c in candles_map.items() if not c]
        if missing:
            print(f"  [{interval}] Missing cache for {missing}. Run fetch_history.py --interval {interval}")
            continue

        total_candles = sum(len(c) for c in candles_map.values())
        print(f"  [{interval}] {total_candles:,} total candles across {len(candles_map)} pairs ...", end="", flush=True)

        for strategy in STRATEGIES:
            all_results[interval][strategy.name] = {}
            for symbol, candles in candles_map.items():
                m = run_backtest(strategy, candles, symbol=symbol,
                                 min_confidence=MIN_CONFIDENCE)
                all_results[interval][strategy.name][symbol] = m
        print(" done")

    # ── Per-interval aggregate table ────────────────────────────────────────
    print("\n" + "=" * 80)
    print("  INTERVAL AGGREGATE RANKING")
    print("=" * 80)
    header = (f"  {'Interval':<8}  {'Trades':>6}  {'AvgWin':>7}  "
              f"{'TotalPnL':>10}  {'Positive':>8}  {'Meaningful':>10}")
    print(header)
    print("  " + "-" * 75)

    interval_stats = []
    for interval, strat_map in all_results.items():
        all_m = [m for sm in strat_map.values() for m in sm.values()]
        stats = _agg_stats(all_m)
        stats["interval"] = interval
        interval_stats.append(stats)
        print(
            f"  {interval:<8}  {stats['total_trades']:>6}  "
            f"{stats['avg_win_rate']:>6.1%}  "
            f"{stats['total_pnl']:>+10.4f}  "
            f"{stats['positive_combos']:>6}/{stats['combos']}  "
            f"{stats['meaningful_combos']:>7}/{stats['combos']}"
        )

    interval_stats.sort(key=lambda x: x["total_pnl"], reverse=True)
    best_interval = interval_stats[0]["interval"]

    # ── Per-strategy best interval ───────────────────────────────────────────
    print("\n" + "=" * 80)
    print("  BEST INTERVAL PER STRATEGY")
    print("=" * 80)
    strategy_best: dict[str, dict] = {}
    for strategy in STRATEGIES:
        sname = strategy.name
        best_row = None
        best_pnl = float("-inf")
        for interval, strat_map in all_results.items():
            if sname not in strat_map:
                continue
            sym_metrics = strat_map[sname]
            top = max(sym_metrics.values(), key=lambda m: m.net_pnl_usdt)
            if top.net_pnl_usdt > best_pnl:
                best_pnl = top.net_pnl_usdt
                best_row = {"interval": interval, "metrics": top}
        if best_row:
            strategy_best[sname] = best_row
            m = best_row["metrics"]
            flag = " ← best" if best_row["interval"] == best_interval else ""
            print(f"  {sname:<22}  {best_row['interval']:<4}  → {m.symbol}  "
                  f"pnl={m.net_pnl_usdt:>+.4f}  win={m.win_rate:.0%}  "
                  f"trades={m.total_trades}{flag}")

    # ── Full leaderboard for best interval ──────────────────────────────────
    print(f"\n{'=' * 80}")
    print(f"  DETAILED LEADERBOARD — Best Interval: {best_interval}")
    print(f"{'=' * 80}")
    detail_header = (
        f"  {'Symbol':<10}  {'Strategy':<22}  {'Trades':>6}  "
        f"{'WinRate':>7}  {'NetPnL':>8}  {'MaxDD':>6}  {'ProfFactor':>10}"
    )
    sep = "  " + "-" * 76
    print(detail_header)
    print(sep)

    if best_interval in all_results:
        all_m_best = [
            m for sm in all_results[best_interval].values() for m in sm.values()
        ]
        for m in sorted(all_m_best, key=lambda x: x.net_pnl_usdt, reverse=True):
            pf = f"{m.profit_factor:.2f}" if m.profit_factor != math.inf else "   inf"
            trades_note = "  *" if m.total_trades < MIN_TRADES_THRESHOLD else ""
            print(
                f"  {m.symbol:<10}  {m.strategy_name:<22}  {m.total_trades:>6}  "
                f"{m.win_rate:>6.1%}  {m.net_pnl_usdt:>+8.4f}  "
                f"{m.max_drawdown_pct:>5.1%}  {pf:>10}{trades_note}"
            )
    print(sep)
    print("  * = fewer than 3 trades (not statistically reliable)")

    # ── Cross-interval comparison for each pair×strategy ────────────────────
    print(f"\n{'=' * 80}")
    print("  CROSS-INTERVAL COMPARISON (best PnL per symbol×strategy)")
    print(f"{'=' * 80}")
    print(f"  {'Symbol':<10}  {'Strategy':<22}  " +
          "  ".join(f"{iv:>7}" for iv in args.intervals))
    print("  " + "-" * (34 + 9 * len(args.intervals)))

    for symbol in symbols:
        for strategy in STRATEGIES:
            row = f"  {symbol:<10}  {strategy.name:<22}"
            for interval in args.intervals:
                if interval in all_results and strategy.name in all_results[interval]:
                    m = all_results[interval][strategy.name].get(symbol)
                    if m:
                        marker = "+" if m.net_pnl_usdt > 0 else " "
                        row += f"  {marker}{m.net_pnl_usdt:>+6.3f}"
                    else:
                        row += f"  {'N/A':>7}"
                else:
                    row += f"  {'N/A':>7}"
            print(row)

    # ── Verdict ──────────────────────────────────────────────────────────────
    print(f"\n{'=' * 80}")
    print(f"  VERDICT")
    print(f"{'=' * 80}")
    print(f"  Best interval by aggregate PnL: {best_interval}")

    top = interval_stats[0]
    print(f"  {best_interval}: total_pnl={top['total_pnl']:+.4f}  "
          f"trades={top['total_trades']}  "
          f"win={top['avg_win_rate']:.1%}  "
          f"positive={top['positive_combos']}/{top['combos']} combos")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
