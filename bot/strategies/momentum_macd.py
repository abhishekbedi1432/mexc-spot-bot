"""
Momentum MACD Strategy
Entry:  MACD histogram turns positive (prev < 0, now > 0)  AND  RSI(14) > 50
Exit:   Histogram turns negative  OR  ATR trail hit
SL/TP:  1× ATR / 1.5× ATR
"""
from __future__ import annotations

from typing import List

from bot import config
from bot import indicators as ind
from bot.strategies.base import Signal, Strategy


class MomentumMACDStrategy(Strategy):
    name = "momentum_macd"

    def __init__(
        self,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
        rsi_period: int = 14,
        rsi_threshold: float = 50.0,
        atr_period: int = 14,
    ):
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
        self.rsi_period = rsi_period
        self.rsi_threshold = rsi_threshold
        self.atr_period = atr_period

    def decide(self, candles: List[dict]) -> Signal:
        try:
            closes = [float(c["close"]) for c in candles]
            macd_data = ind.macd(closes, self.macd_fast, self.macd_slow, self.macd_signal)
            rsi_vals = ind.rsi(closes, self.rsi_period)
            atr_vals = ind.atr(candles, self.atr_period)

            hist_now = macd_data["histogram"][-1]
            hist_prev = macd_data["histogram"][-2]
            rsi_now = rsi_vals[-1]
            atr_now = atr_vals[-1]

            if any(v is None for v in [hist_now, hist_prev, rsi_now, atr_now]):
                return Signal(action="HOLD", confidence=0.0, reason="warmup — indicators not ready")

            histogram_flip = hist_prev < 0 and hist_now > 0  # type: ignore[operator]
            momentum_ok = rsi_now > self.rsi_threshold  # type: ignore[operator]

            if histogram_flip and momentum_ok:
                close = closes[-1]
                entry = close * (1 - config.ENTRY_OFFSET_PCT)
                sl = entry - config.SL_ATR_MULT * atr_now  # type: ignore[operator]
                tp = entry + config.TP_ATR_MULT * atr_now  # type: ignore[operator]
                conf = min(1.0, (rsi_now - 50) / 50)  # type: ignore[operator]
                return Signal(
                    action="BUY",
                    confidence=round(conf, 3),
                    reason=f"MACD hist flip +, RSI={rsi_now:.1f}>{self.rsi_threshold}",
                    entry_price=round(entry, 8),
                    sl_price=round(sl, 8),
                    tp_price=round(tp, 8),
                )

            return Signal(
                action="HOLD",
                confidence=0.0,
                reason=f"hist={hist_now:.6f}, RSI={rsi_now:.1f}",
            )

        except Exception as exc:  # noqa: BLE001
            return Signal(action="HOLD", confidence=0.0, reason=f"error: {exc}")
