"""
Backtester — walk-forward simulation over historical klines.

Simulation rules (matches live bot behaviour):
- Sliding 150-candle window fed to strategy.decide() — mirrors KLINE_LIMIT
- Entry: LIMIT order assumed filled at signal.entry_price (maker fee 0.10%)
- Exit: TP limit order → maker fee 0.10%; SL market order → taker fee 0.10%
- Both SL+TP on same candle → SL wins (conservative)
- Unclosed position at end of data → closed at last close (mark-to-market)
- Max 1 open position at a time; new signal ignored while position is open
- step_size auto-detected from price magnitude if not supplied

Usage:
  from bot.backtester import run_backtest, print_leaderboard
  metrics = run_backtest(strategy, candles, symbol="BTCUSDT")
  print_leaderboard([metrics, ...])
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from bot import config
from bot.risk import calc_quantity
from bot.strategies.base import Strategy

# How many candles to feed the strategy per tick (mirrors live bot)
WINDOW = 150
# Minimum candles before we start iterating (allow all indicators to warm up)
WARMUP = 50


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Trade:
    """Represents a single completed backtest trade."""
    symbol: str
    entry_price: float
    exit_price: float
    quantity: float
    side: str            # 'BUY'
    exit_reason: str     # 'TP' | 'SL' | 'END_OF_DATA'
    entry_idx: int
    exit_idx: int
    net_pnl_usdt: float = 0.0

    @property
    def pnl_pct(self) -> float:
        if self.entry_price == 0:
            return 0.0
        return (self.exit_price - self.entry_price) / self.entry_price

    @property
    def is_win(self) -> bool:
        return self.net_pnl_usdt > 0


@dataclass
class BacktestMetrics:
    symbol: str
    strategy_name: str
    total_trades: int = 0
    winning_trades: int = 0
    net_pnl_usdt: float = 0.0
    final_capital: float = 0.0
    max_drawdown_pct: float = 0.0
    profit_factor: float = 0.0
    win_rate: float = 0.0
    avg_trade_pnl: float = 0.0
    trades: List[Trade] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "symbol": self.symbol,
            "strategy": self.strategy_name,
            "total_trades": self.total_trades,
            "win_rate": round(self.win_rate, 3),
            "net_pnl_usdt": round(self.net_pnl_usdt, 4),
            "final_capital": round(self.final_capital, 4),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "profit_factor": round(self.profit_factor, 3),
            "avg_trade_pnl": round(self.avg_trade_pnl, 5),
        }


# ---------------------------------------------------------------------------
# Step-size auto-detection
# ---------------------------------------------------------------------------

def _auto_step_size(price: float) -> float:
    """
    Estimate lot step_size from price magnitude.
    This is a reasonable approximation; real values come from /exchangeInfo.
    BTC ~90k  → 0.00001
    ETH ~1.8k → 0.0001
    SOL ~130  → 0.01
    DOGE ~0.18 → 1.0
    """
    if price > 10_000:
        return 0.00001
    if price > 500:
        return 0.0001
    if price > 10:
        return 0.01
    if price > 0.1:
        return 0.1
    return 1.0


# ---------------------------------------------------------------------------
# Fee model
# ---------------------------------------------------------------------------

def _calc_trade_pnl(
    entry: float,
    exit_price: float,
    qty: float,
    exit_reason: str,
) -> float:
    """
    Net PnL after fees.
    Entry:  LIMIT maker → MAKER_FEE
    TP exit: LIMIT maker → MAKER_FEE
    SL exit: market taker → TAKER_FEE
    END_OF_DATA: treat as taker (market close)
    """
    gross = (exit_price - entry) * qty
    entry_fee = config.MAKER_FEE * entry * qty
    if exit_reason == "TP":
        exit_fee = config.MAKER_FEE * exit_price * qty
    else:  # SL or END_OF_DATA
        exit_fee = config.TAKER_FEE * exit_price * qty
    return gross - entry_fee - exit_fee


# ---------------------------------------------------------------------------
# Max drawdown from equity curve
# ---------------------------------------------------------------------------

def _max_drawdown(equity: List[float]) -> float:
    """Return max peak-to-trough drawdown as a fraction (0.0 – 1.0)."""
    if not equity:
        return 0.0
    peak = equity[0]
    max_dd = 0.0
    for val in equity:
        if val > peak:
            peak = val
        if peak > 0:
            dd = (peak - val) / peak
            max_dd = max(max_dd, dd)
    return max_dd


# ---------------------------------------------------------------------------
# Core walk-forward loop
# ---------------------------------------------------------------------------

def run_backtest(
    strategy: Strategy,
    candles: List[dict],
    symbol: str = "UNKNOWN",
    initial_capital: float = 10.0,
    step_size: Optional[float] = None,
) -> BacktestMetrics:
    """
    Walk-forward simulation over `candles`.
    Returns BacktestMetrics with full trade log and summary stats.
    """
    if len(candles) < WARMUP + 2:
        return BacktestMetrics(
            symbol=symbol,
            strategy_name=strategy.name,
            final_capital=initial_capital,
        )

    # Auto-detect step_size from first candle's close price
    if step_size is None:
        step_size = _auto_step_size(float(candles[0]["close"]))

    capital = initial_capital
    equity_curve: List[float] = [capital]
    trades: List[Trade] = []
    position: Optional[dict] = None

    for i in range(WARMUP, len(candles)):
        candle = candles[i]

        # ── Manage open position ──────────────────────────────────────────
        if position is not None:
            h = float(candle["high"])
            l = float(candle["low"])
            tp_hit = h >= position["tp"]
            sl_hit = l <= position["sl"]

            if tp_hit or sl_hit:
                if sl_hit and tp_hit:
                    # Both on same candle — SL wins (conservative)
                    exit_price = position["sl"]
                    exit_reason = "SL"
                elif tp_hit:
                    exit_price = position["tp"]
                    exit_reason = "TP"
                else:
                    exit_price = position["sl"]
                    exit_reason = "SL"

                net = _calc_trade_pnl(
                    position["entry_price"], exit_price, position["qty"], exit_reason
                )
                capital += net
                equity_curve.append(capital)

                trades.append(Trade(
                    symbol=symbol,
                    entry_price=position["entry_price"],
                    exit_price=exit_price,
                    quantity=position["qty"],
                    side="BUY",
                    exit_reason=exit_reason,
                    entry_idx=position["entry_idx"],
                    exit_idx=i,
                    net_pnl_usdt=net,
                ))
                position = None
            continue  # Don't look for new entries while managing a position

        # ── Look for new entry ────────────────────────────────────────────
        # Feed a sliding window of up to WINDOW candles
        start = max(0, i - WINDOW + 1)
        window = candles[start : i + 1]
        signal = strategy.decide(window)

        if (
            signal.action == "BUY"
            and signal.entry_price is not None
            and signal.sl_price is not None
            and signal.tp_price is not None
            and signal.entry_price > 0
            and signal.sl_price < signal.entry_price
            and signal.tp_price > signal.entry_price
        ):
            notional = min(config.MAX_TRADE_USDT, capital * config.CAPITAL_FRACTION)
            if notional < 1.0:  # below absolute floor
                continue
            qty = calc_quantity(notional, signal.entry_price, step_size)
            if qty <= 0:
                continue

            position = {
                "entry_price": signal.entry_price,
                "qty": qty,
                "sl": signal.sl_price,
                "tp": signal.tp_price,
                "entry_idx": i,
            }

    # ── Mark-to-market: close any open position at end of data ────────────
    if position is not None:
        exit_price = float(candles[-1]["close"])
        net = _calc_trade_pnl(
            position["entry_price"], exit_price, position["qty"], "END_OF_DATA"
        )
        capital += net
        equity_curve.append(capital)
        trades.append(Trade(
            symbol=symbol,
            entry_price=position["entry_price"],
            exit_price=exit_price,
            quantity=position["qty"],
            side="BUY",
            exit_reason="END_OF_DATA",
            entry_idx=position["entry_idx"],
            exit_idx=len(candles) - 1,
            net_pnl_usdt=net,
        ))

    # ── Compute aggregate metrics ─────────────────────────────────────────
    n = len(trades)
    wins = [t for t in trades if t.is_win]
    losses = [t for t in trades if not t.is_win]

    gross_profit = sum(t.net_pnl_usdt for t in wins)
    gross_loss = abs(sum(t.net_pnl_usdt for t in losses))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (
        math.inf if gross_profit > 0 else 0.0
    )

    return BacktestMetrics(
        symbol=symbol,
        strategy_name=strategy.name,
        total_trades=n,
        winning_trades=len(wins),
        net_pnl_usdt=capital - initial_capital,
        final_capital=capital,
        max_drawdown_pct=_max_drawdown(equity_curve),
        profit_factor=profit_factor,
        win_rate=len(wins) / n if n > 0 else 0.0,
        avg_trade_pnl=(capital - initial_capital) / n if n > 0 else 0.0,
        trades=trades,
    )


# ---------------------------------------------------------------------------
# Leaderboard printer
# ---------------------------------------------------------------------------

def print_leaderboard(all_metrics: List[BacktestMetrics]) -> None:
    """Print a formatted leaderboard table to stdout."""
    header = (
        f"{'Symbol':<10}  {'Strategy':<22}  {'Trades':>6}  "
        f"{'WinRate':>7}  {'NetPnL':>8}  {'MaxDD':>7}  {'ProfFactor':>10}"
    )
    sep = "-" * len(header)
    print(sep)
    print(header)
    print(sep)
    for m in sorted(all_metrics, key=lambda x: x.net_pnl_usdt, reverse=True):
        pf = f"{m.profit_factor:.2f}" if m.profit_factor != math.inf else "  inf"
        print(
            f"{m.symbol:<10}  {m.strategy_name:<22}  {m.total_trades:>6}  "
            f"{m.win_rate:>6.1%}  {m.net_pnl_usdt:>+8.4f}  "
            f"{m.max_drawdown_pct:>6.1%}  {pf:>10}"
        )
    print(sep)
