"""
Paper Trader — simulates live fills against real market data.
Shares the executor code path; flip DRY_RUN=false to go live.
Phase 0: scaffold only. Full implementation in Phase 4.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from bot import config
from bot.strategies.base import Signal

logger = logging.getLogger(__name__)

PAPER_LOG = config.LOGS_DIR / "paper.jsonl"


@dataclass
class PaperPosition:
    symbol: str
    entry_price: float
    quantity: float
    sl_price: float
    tp_price: float
    entry_time: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "OPEN"   # OPEN | TP | SL | MANUAL


def log_paper_event(event: Dict[str, Any]) -> None:
    """Append a JSON line to paper.jsonl."""
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(PAPER_LOG, "a") as f:
        f.write(json.dumps(event) + "\n")


def simulate_tick(
    position: Optional[PaperPosition],
    candle: dict,
    signal: Signal,
    capital: float,
) -> Dict[str, Any]:
    """
    Given a current candle and strategy signal, update paper position.
    Phase 0: stub returns HOLD.
    Phase 4: full implementation.
    """
    # TODO (Phase 4): implement fill simulation
    return {"action": "HOLD", "reason": "paper_trader not yet implemented (Phase 4)"}
