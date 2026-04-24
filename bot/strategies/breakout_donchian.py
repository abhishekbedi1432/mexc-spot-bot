"""
Breakout Donchian Strategy
Entry:  close breaks above 20-bar Donchian high  AND  volume > 1.5× 20-bar avg volume
Exit:   ATR trail or Donchian lower re-entry
SL/TP:  1× ATR / 1.5× ATR
"""
from __future__ import annotations

from typing import List

from bot import config
from bot import indicators as ind
from bot.strategies.base import Signal, Strategy

VOLUME_MULT = 1.5


class BreakoutDonchianStrategy(Strategy):
    name = "breakout_donchian"

    def __init__(
        self,
        period: int = 20,
        volume_mult: float = VOLUME_MULT,
        atr_period: int = 14,
    ):
        self.period = period
        self.volume_mult = volume_mult
        self.atr_period = atr_period

    def decide(self, candles: List[dict]) -> Signal:
        try:
            dc = ind.donchian(candles, self.period)
            vol_sma = ind.volume_sma(candles, self.period)
            atr_vals = ind.atr(candles, self.atr_period)

            # Use second-to-last candle for the channel (avoid look-ahead)
            dc_upper_prev = dc["upper"][-2]
            current_close = float(candles[-1]["close"])
            current_vol = float(candles[-1]["volume"])
            avg_vol = vol_sma[-2]
            atr_now = atr_vals[-1]

            if any(v is None for v in [dc_upper_prev, avg_vol, atr_now]):
                return Signal(action="HOLD", confidence=0.0, reason="warmup — indicators not ready")

            breakout = current_close > dc_upper_prev  # type: ignore[operator]
            high_volume = current_vol > self.volume_mult * avg_vol  # type: ignore[operator]

            if breakout and high_volume:
                entry = current_close * (1 - config.ENTRY_OFFSET_PCT)
                sl = entry - config.SL_ATR_MULT * atr_now  # type: ignore[operator]
                tp = entry + config.TP_ATR_MULT * atr_now  # type: ignore[operator]
                vol_ratio = current_vol / avg_vol  # type: ignore[operator]
                conf = min(1.0, (vol_ratio - 1.0) / 2.0)
                return Signal(
                    action="BUY",
                    confidence=round(conf, 3),
                    reason=f"Donchian breakout close={current_close:.4f}>{dc_upper_prev:.4f}, vol×{vol_ratio:.1f}",
                    entry_price=round(entry, 8),
                    sl_price=round(sl, 8),
                    tp_price=round(tp, 8),
                )

            return Signal(
                action="HOLD",
                confidence=0.0,
                reason=f"close={current_close:.4f} <= DC_upper={dc_upper_prev:.4f} or low vol",
            )

        except Exception as exc:  # noqa: BLE001
            return Signal(action="HOLD", confidence=0.0, reason=f"error: {exc}")
