"""
Risk management module.
Handles position sizing, min-notional, spread check, daily-loss kill-switch.
No network calls — pure calculation.
"""
from __future__ import annotations

from typing import Optional, Tuple

from bot import config


def calc_notional(capital: float) -> float:
    """Return safe per-trade notional in USDT."""
    return min(config.MAX_TRADE_USDT, capital * config.CAPITAL_FRACTION)


def calc_quantity(notional: float, price: float, step_size: float) -> float:
    """
    Return quantity floored to exchange step_size.
    quantity = floor(notional / price / step_size) * step_size
    """
    if price <= 0 or step_size <= 0:
        raise ValueError(f"Invalid price={price} or step_size={step_size}")
    raw = notional / price
    steps = int(raw / step_size)
    return round(steps * step_size, 8)


def is_spread_ok(bid: float, ask: float) -> bool:
    """Return True if spread is within acceptable threshold."""
    if bid <= 0:
        return False
    spread_pct = (ask - bid) / bid
    return spread_pct <= config.MAX_SPREAD_PCT


def is_profit_viable(
    entry: float,
    sl: float,
    tp: float,
    notional: float,
) -> bool:
    """
    Return True if expected profit (at TP) exceeds 2× round-trip fees.
    Both legs assumed at maker rate.
    """
    expected_profit = (tp - entry) / entry * notional
    round_trip_cost = config.ROUND_TRIP_FEE * notional
    return expected_profit >= config.MIN_PROFIT_FEE_MULTIPLE * round_trip_cost


def check_daily_loss(
    start_equity: float,
    current_equity: float,
) -> Tuple[bool, str]:
    """
    Returns (kill_switch_triggered, reason).
    If today's loss >= DAILY_LOSS_LIMIT → True.
    """
    if start_equity <= 0:
        return False, "start_equity invalid"
    pnl_pct = (current_equity - start_equity) / start_equity
    if pnl_pct <= config.DAILY_LOSS_LIMIT:
        return True, f"Daily loss {pnl_pct*100:.2f}% <= {config.DAILY_LOSS_LIMIT*100:.0f}% limit"
    return False, f"PnL={pnl_pct*100:.2f}%"


def validate_min_notional(notional: float, min_notional: float) -> bool:
    """Check order meets exchange minimum notional."""
    return notional >= min_notional
