"""
Executor — places LIMIT entry orders and SL/TP brackets.
Phase 0: stub (all operations are DRY_RUN).
Phase 5+: wired to binance_client with real keys and TRADE permission.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from bot import config
from bot.strategies.base import Signal

logger = logging.getLogger(__name__)


def place_bracket(
    symbol: str,
    signal: Signal,
    quantity: float,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """
    Place LIMIT entry order. SL/TP are tracked in paper_trader for now;
    real bracket orders (OCO) added in Phase 6.

    Returns order response dict.
    """
    if signal.entry_price is None:
        raise ValueError("Signal has no entry_price")

    from bot import binance_client as bc  # lazy import — avoids network at import time

    logger.info(
        "[%s] %s LIMIT qty=%.8f @ %.8f  SL=%.8f  TP=%.8f  dry=%s",
        symbol,
        signal.action,
        quantity,
        signal.entry_price,
        signal.sl_price or 0,
        signal.tp_price or 0,
        dry_run,
    )

    order = bc.place_limit_order(
        symbol=symbol,
        side=signal.action,
        quantity=quantity,
        price=signal.entry_price,
        dry_run=dry_run,
    )
    return order


def cancel_stale_orders(symbol: str, dry_run: bool = True) -> list:
    """
    Cancel any open orders older than FILL_TIMEOUT_SECONDS.
    Phase 0: returns empty list (no network).
    """
    if dry_run:
        logger.debug("[%s] DRY_RUN: skip cancel_stale_orders", symbol)
        return []

    from bot import binance_client as bc

    open_orders = bc.get_open_orders(symbol)
    cancelled = []
    import time
    now_ms = int(time.time() * 1000)
    for o in open_orders:
        age_s = (now_ms - o["time"]) / 1000
        if age_s > config.FILL_TIMEOUT_SECONDS:
            result = bc.cancel_order(symbol, o["orderId"], dry_run=False)
            cancelled.append(result)
            logger.info("[%s] Cancelled stale order %s (age=%.0fs)", symbol, o["orderId"], age_s)
    return cancelled
