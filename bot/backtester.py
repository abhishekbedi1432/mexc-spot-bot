"""
Backtester — replays a strategy over historical klines.
Phase 0: scaffold only. Full implementation in Phase 2.

Usage (Phase 2+):
  from bot.backtester import run_backtest
  metrics = run_backtest(strategy, candles)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from bot import config
from bot.strategies.base import Signal, Strategy


@dataclass
class Trade:
    """Represents a single completed backtest trade."""
    symbol: str
    entry_price: float
    exit_price: float
    quantity: float
    side: str             # 'BUY'
    exit_reason: str      # 'TP' | 'SL' | 'SIGNAL_EXIT' | 'END_OF_DATA'
    entry_idx: int
    exit_idx: int

    @property
    def pnl_usdt(self) -> float:
        notional = self.entry_price * self.quantity
        gross = (self.exit_price - self.entry_price) * self.quantity
        fees = config.ROUND_TRIP_FEE * notional
        return gross - fees

    @property
    def pnl_pct(self) -> float:
        if self.entry_price == 0:
            return 0.0
        return (self.exit_price - self.entry_price) / self.entry_price


@dataclass
class BacktestMetrics:
    symbol: str
    strategy_name: str
    total_trades: int = 0
    winning_trades: int = 0
    net_pnl_usdt: float = 0.0
    max_drawdown_pct: float = 0.0
    profit_factor: float = 0.0
    win_rate: float = 0.0
    trades: List[Trade] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "symbol": self.symbol,
            "strategy": self.strategy_name,
            "total_trades": self.total_trades,
            "win_rate": round(self.win_rate, 3),
            "net_pnl_usdt": round(self.net_pnl_usdt, 4),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "profit_factor": round(self.profit_factor, 3),
        }


def run_backtest(
    strategy: Strategy,
    candles: List[dict],
    symbol: str = "UNKNOWN",
    initial_capital: float = 10.0,
    step_size: float = 0.00001,  # fetched from exchangeInfo in Phase 2
) -> BacktestMetrics:
    """
    Walk-forward simulation over `candles`.
    Phase 0: returns empty metrics.
    Phase 2: full implementation.
    """
    # TODO (Phase 2): implement walk-forward loop
    return BacktestMetrics(symbol=symbol, strategy_name=strategy.name)
