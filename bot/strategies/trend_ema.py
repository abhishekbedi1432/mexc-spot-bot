"""
Trend EMA Strategy
Entry:  EMA(9) crosses above EMA(21)  AND  ADX(14) > 20 (trend is strong)
Exit:   EMA(9) crosses below EMA(21)  OR   ATR trail hit
SL/TP:  1× ATR / 1.5× ATR
"""
from __future__ import annotations

from typing import List

from bot import config
from bot import indicators as ind
from bot.strategies.base import Signal, Strategy


class TrendEMAStrategy(Strategy):
    name = "trend_ema"

    def __init__(
        self,
        fast: int = 9,
        slow: int = 21,
        adx_period: int = 14,
        adx_threshold: float = 20.0,
        atr_period: int = 14,
    ):
        self.fast = fast
        self.slow = slow
        self.adx_period = adx_period
        self.adx_threshold = adx_threshold
        self.atr_period = atr_period

    def decide(self, candles: List[dict]) -> Signal:
        try:
            closes = [float(c["close"]) for c in candles]
            ema_fast = ind.ema(closes, self.fast)
            ema_slow = ind.ema(closes, self.slow)
            adx_vals = ind.adx(candles, self.adx_period)
            atr_vals = ind.atr(candles, self.atr_period)

            ef_now = ema_fast[-1]
            es_now = ema_slow[-1]
            ef_prev = ema_fast[-2]
            es_prev = ema_slow[-2]
            adx_now = adx_vals[-1]
            atr_now = atr_vals[-1]

            if any(v is None for v in [ef_now, es_now, ef_prev, es_prev, adx_now, atr_now]):
                return Signal(action="HOLD", confidence=0.0, reason="warmup — indicators not ready")

            # Bullish crossover: fast crossed above slow
            crossover = ef_prev <= es_prev and ef_now > es_now  # type: ignore[operator]
            strong_trend = adx_now >= self.adx_threshold  # type: ignore[operator]

            if crossover and strong_trend:
                close = closes[-1]
                entry = close * (1 - config.ENTRY_OFFSET_PCT)
                sl = entry - config.SL_ATR_MULT * atr_now  # type: ignore[operator]
                tp = entry + config.TP_ATR_MULT * atr_now  # type: ignore[operator]
                conf = min(1.0, adx_now / 50.0)  # type: ignore[operator]
                return Signal(
                    action="BUY",
                    confidence=round(conf, 3),
                    reason=f"EMA({self.fast})×EMA({self.slow}) crossover, ADX={adx_now:.1f}",
                    entry_price=round(entry, 8),
                    sl_price=round(sl, 8),
                    tp_price=round(tp, 8),
                )

            return Signal(
                action="HOLD",
                confidence=0.0,
                reason=f"EMA gap={ef_now - es_now:.4f}, ADX={adx_now:.1f}",  # type: ignore[operator]
            )

        except Exception as exc:  # noqa: BLE001
            return Signal(action="HOLD", confidence=0.0, reason=f"error: {exc}")
