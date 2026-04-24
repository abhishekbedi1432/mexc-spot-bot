"""
Base strategy interface and Signal dataclass.
All strategies must implement this interface.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Signal:
    """Output of a strategy's decide() call."""
    action: str          # 'BUY' | 'SELL' | 'HOLD'
    confidence: float    # 0.0 – 1.0
    reason: str          # Human-readable explanation for logs
    sl_price: Optional[float] = None   # Stop-loss absolute price
    tp_price: Optional[float] = None   # Take-profit absolute price
    entry_price: Optional[float] = None  # Suggested LIMIT entry price


class Strategy:
    """
    Interface all strategies must implement.
    name: short slug used in config/chosen_strategies.json
    """
    name: str = "base"

    def decide(self, candles: List[dict]) -> Signal:
        """
        Given a list of closed candles (oldest → newest),
        return a Signal. Must never raise — return HOLD on error.
        """
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"<Strategy name={self.name}>"
