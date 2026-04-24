"""
Main orchestrator — single-shot 5-min tick.
Invoked by GitHub Actions cron every 5 minutes.

Flow:
  1. Clock skew check
  2. For each pair: fetch klines → run strategy → evaluate signal
  3. Account balance + open orders check (Phase 5+)
  4. Risk checks → execute or HOLD
  5. Daily loss kill-switch
  6. Log decision envelope to logs/decisions.jsonl
"""
from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from bot import config
from bot import risk
from bot.strategies.base import Signal
from bot.strategies.mean_reversion import MeanReversionStrategy
from bot.strategies.trend_ema import TrendEMAStrategy
from bot.strategies.breakout_donchian import BreakoutDonchianStrategy
from bot.strategies.momentum_macd import MomentumMACDStrategy

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("bot.main")

DECISIONS_LOG = config.LOGS_DIR / "decisions.jsonl"

STRATEGY_REGISTRY = {
    "mean_reversion": MeanReversionStrategy,
    "trend_ema": TrendEMAStrategy,
    "breakout_donchian": BreakoutDonchianStrategy,
    "momentum_macd": MomentumMACDStrategy,
}


def _log_decision(event: Dict[str, Any]) -> None:
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(DECISIONS_LOG, "a") as f:
        f.write(json.dumps(event) + "\n")


def _make_event(
    symbol: str,
    signal: Signal,
    dry_run: bool,
    extra: Optional[Dict] = None,
) -> Dict[str, Any]:
    event: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "action": signal.action,
        "confidence": signal.confidence,
        "reason": signal.reason,
        "entry_price": signal.entry_price,
        "sl_price": signal.sl_price,
        "tp_price": signal.tp_price,
        "dry_run": dry_run,
    }
    if extra:
        event.update(extra)
    return event


def run_tick() -> int:
    """Execute one tick. Returns 0 on success, 1 on fatal error."""
    logger.info("=== Tick start | DRY_RUN=%s ===", config.DRY_RUN)

    # --- Phase 1+: clock skew check ---
    # from bot import binance_client as bc
    # server_ms = bc.get_server_time()
    # skew = abs(server_ms - int(time.time() * 1000))
    # if skew > 1000: logger.warning("Clock skew %dms", skew)

    chosen = config.load_chosen_strategies()
    if not chosen:
        logger.info("No chosen strategies yet (pre-Phase 2). Running all strategies in DRY_RUN.")
        # Use all strategies for initial paper run
        chosen = {pair: "mean_reversion" for pair in config.PAIRS}

    for symbol in config.PAIRS:
        strategy_name = chosen.get(symbol, "mean_reversion")
        strategy_cls = STRATEGY_REGISTRY.get(strategy_name)
        if strategy_cls is None:
            logger.error("Unknown strategy '%s' for %s — skipping", strategy_name, symbol)
            continue

        strategy = strategy_cls()

        # --- Phase 1+: fetch real klines ---
        # candles = bc.get_klines(symbol, config.KLINE_INTERVAL, config.KLINE_LIMIT)
        # For Phase 0: emit HOLD with placeholder
        signal = Signal(
            action="HOLD",
            confidence=0.0,
            reason="Phase 0 — no klines fetched yet",
        )

        # --- Signal quality gates (active Phase 3+) ---
        skip_reason: Optional[str] = None
        if signal.action == "BUY":
            if signal.confidence < config.MIN_CONFIDENCE:
                skip_reason = f"confidence {signal.confidence:.2f} < MIN_CONFIDENCE {config.MIN_CONFIDENCE}"
            elif signal.entry_price and signal.sl_price and signal.tp_price:
                notional = min(config.MAX_TRADE_USDT, config.CAPITAL_USDT * config.CAPITAL_FRACTION)
                if not risk.is_profit_viable(signal.entry_price, signal.sl_price, signal.tp_price, notional):
                    skip_reason = "expected profit < 2× round-trip fees"

        if skip_reason:
            signal = Signal(action="HOLD", confidence=0.0, reason=f"filtered: {skip_reason}")
            logger.debug("[%s] Signal filtered: %s", symbol, skip_reason)

        event = _make_event(symbol, signal, dry_run=config.DRY_RUN)
        _log_decision(event)
        logger.info("[%s] %s | %s", symbol, signal.action, signal.reason)

    logger.info("=== Tick complete ===")
    return 0


if __name__ == "__main__":
    sys.exit(run_tick())
