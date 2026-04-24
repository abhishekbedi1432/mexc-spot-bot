#!/usr/bin/env python3
"""
Grid search optimizer for TP/SL multipliers.
Tests all combinations of TP_MULT x SL_MULT across all strategies and pairs.
Runs with min_confidence=0.3 (the filtered baseline).

Usage:
  python scripts/optimize_params.py
  python scripts/optimize_params.py --symbol BTCUSDT
  python scripts/optimize_params.py --strategy mean_reversion

Output: ranked table of (tp_mult, sl_mult) combinations by aggregate net PnL.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot import config
from bot.backtester import run_backtest
from bot.data import load_candles
from bot.strategies.mean_reversion import MeanReversionStrategy
from bot.strategies.trend_ema import TrendEMAStrategy
from bot.strategies.breakout_donchian import BreakoutDonchianStrategy
from bot.strategies.momentum_macd import MomentumMACDStrategy

# Grid to search
TP_MULTS = [1.5, 2.0, 2.5, 3.0]
SL_MULTS = [0.75, 1.0, 1.25]

MIN_CONFIDENCE = 0.3

STRATEGY_FACTORIES = {
    "mean_reversion": lambda sl, tp: MeanReversionStrategy(sl_mult=sl, tp_mult=tp),
    "trend_ema":      lambda sl, tp: TrendEMAStrategy(sl_mult=sl, tp_mult=tp),
    "breakout_donchian": lambda sl, tp: BreakoutDonchianStrategy(sl_mult=sl, tp_mult=tp),
    "momentum_macd":  lambda sl, tp: MomentumMACDStrategy(sl_mult=sl, tp_mult=tp),
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Grid search TP/SL multipliers")
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--strategy", default=None)
    args = parser.parse_args()

    symbols = [args.symbol] if args.symbol else config.PAIRS
    strategy_names = [args.strategy] if args.strategy else list(STRATEGY_FACTORIES.keys())

    # Pre-load candles
    candles_map = {}
    for s in symbols:
        c = load_candles(s)
        if c:
            candles_map[s] = c
        else:
            print(f"  [{s}] No cache — skipping")

    if not candles_map:
        print("No data. Run: python scripts/fetch_history.py")
        return 1

    print(f"\nGrid search: {len(TP_MULTS)}×{len(SL_MULTS)} multiplier combos × "
          f"{len(strategy_names)} strategies × {len(candles_map)} pairs\n"
          f"min_confidence={MIN_CONFIDENCE}\n")

    # Results: (tp_mult, sl_mult) -> {strategy_name -> {symbol -> metrics}}
    results: dict = {}

    total_runs = len(TP_MULTS) * len(SL_MULTS) * len(strategy_names) * len(candles_map)
    run = 0
    for tp in TP_MULTS:
        for sl in SL_MULTS:
            key = (tp, sl)
            results[key] = {}
            for sname in strategy_names:
                factory = STRATEGY_FACTORIES[sname]
                results[key][sname] = {}
                for symbol, candles in candles_map.items():
                    strategy = factory(sl, tp)
                    m = run_backtest(
                        strategy, candles, symbol=symbol,
                        min_confidence=MIN_CONFIDENCE,
                    )
                    results[key][sname][symbol] = m
                    run += 1
            # Progress
            done = sum(1 for t2 in TP_MULTS for s2 in SL_MULTS
                       if (t2 < tp) or (t2 == tp and s2 <= sl))
            print(f"  Progress: {done}/{len(TP_MULTS)*len(SL_MULTS)} combos ...", end="\r")

    print()

    # Aggregate: for each (tp,sl) combo → sum net_pnl across all strategies x pairs
    agg: list[dict] = []
    for (tp, sl), strat_map in results.items():
        total_pnl = sum(
            m.net_pnl_usdt
            for sm in strat_map.values()
            for m in sm.values()
        )
        total_trades = sum(
            m.total_trades
            for sm in strat_map.values()
            for m in sm.values()
        )
        win_rate_sum = sum(
            m.win_rate * m.total_trades
            for sm in strat_map.values()
            for m in sm.values()
            if m.total_trades > 0
        )
        total_traded = sum(
            m.total_trades
            for sm in strat_map.values()
            for m in sm.values()
        )
        avg_win_rate = win_rate_sum / total_traded if total_traded > 0 else 0.0

        # Best per-strategy PnL under this combo
        best_per_strategy = {
            sname: max(sm.values(), key=lambda m: m.net_pnl_usdt)
            for sname, sm in strat_map.items()
        }

        agg.append({
            "tp": tp, "sl": sl,
            "total_pnl": total_pnl,
            "total_trades": total_trades,
            "avg_win_rate": avg_win_rate,
            "rr": round(tp / sl, 2),
            "best_per_strategy": best_per_strategy,
        })

    agg.sort(key=lambda x: x["total_pnl"], reverse=True)

    # ── Aggregate leaderboard ──────────────────────────────────────────────
    print("=" * 75)
    print(f"  AGGREGATE RANKING  (sum of net PnL across all strategies × pairs)")
    print("=" * 75)
    header = f"  {'TP':>4}  {'SL':>4}  {'RR':>4}  {'Trades':>6}  {'AvgWin':>7}  {'TotalPnL':>10}"
    print(header)
    print("  " + "-" * 70)
    for row in agg:
        print(f"  {row['tp']:>4.1f}  {row['sl']:>4.2f}  {row['rr']:>4.2f}  "
              f"{row['total_trades']:>6}  {row['avg_win_rate']:>6.1%}  "
              f"{row['total_pnl']:>+10.4f}")

    # ── Per-strategy best combo ───────────────────────────────────────────
    print()
    print("=" * 75)
    print("  BEST COMBO PER STRATEGY (by max best-pair PnL)")
    print("=" * 75)
    for sname in strategy_names:
        best_row = max(agg, key=lambda r: r["best_per_strategy"][sname].net_pnl_usdt)
        best_m = best_row["best_per_strategy"][sname]
        print(f"  {sname:<22}  TP={best_row['tp']:.1f}  SL={best_row['sl']:.2f}  "
              f"→ {best_m.symbol} {best_m.net_pnl_usdt:>+.4f}  "
              f"win={best_m.win_rate:.0%}  trades={best_m.total_trades}")

    # ── Best single (tp,sl) that maximises number of profitable combos ────
    print()
    best_positive = max(
        agg,
        key=lambda r: sum(
            1 for sm in r["best_per_strategy"].values() if sm.net_pnl_usdt > 0
        )
    )
    positive_count = sum(
        1 for sm in best_positive["best_per_strategy"].values() if sm.net_pnl_usdt > 0
    )
    print(f"  Best for maximising profitable combos: "
          f"TP={best_positive['tp']:.1f}  SL={best_positive['sl']:.2f}  "
          f"→ {positive_count}/{len(strategy_names)} strategies profitable\n")

    winner = agg[0]
    print(f"  RECOMMENDED: TP_ATR_MULT={winner['tp']:.1f}  SL_ATR_MULT={winner['sl']:.2f}  "
          f"(total PnL {winner['total_pnl']:+.4f})\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
