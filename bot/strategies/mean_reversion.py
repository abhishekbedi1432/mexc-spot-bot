"""
Mean Reversion Strategy
Entry:  RSI(14) < 30  AND  close <= lower Bollinger Band(20, 2σ)
Exit:   RSI(14) > 70  OR   close >= upper Bollinger Band
SL/TP:  1× ATR / 1.5× ATR
"""
from __future__ import annotations

from typing import List

from bot import config
from bot import indicators as ind
from bot.strategies.base import Signal, Strategy

_HOLD = Signal(action="HOLD", confidence=0.0, reason="no signal")


class MeanReversionStrategy(Strategy):
    name = "mean_reversion"

    def __init__(
        self,
        rsi_period: int = 14,
        rsi_oversold: float = 30.0,
        rsi_overbought: float = 70.0,
        bb_period: int = 20,
        bb_std: float = 2.0,
        atr_period: int = 14,
        sl_mult: float = None,
        tp_mult: float = None,
    ):
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.atr_period = atr_period
        self.sl_mult = sl_mult if sl_mult is not None else config.SL_ATR_MULT
        self.tp_mult = tp_mult if tp_mult is not None else config.TP_ATR_MULT

    def decide(self, candles: List[dict]) -> Signal:
        try:
            closes = [float(c["close"]) for c in candles]
            rsi_vals = ind.rsi(closes, self.rsi_period)
            bb = ind.bollinger(closes, self.bb_period, self.bb_std)
            atr_vals = ind.atr(candles, self.atr_period)

            current_rsi = rsi_vals[-1]
            current_close = closes[-1]
            lower_band = bb["lower"][-1]
            upper_band = bb["upper"][-1]
            current_atr = atr_vals[-1]

            if any(v is None for v in [current_rsi, lower_band, upper_band, current_atr]):
                return Signal(action="HOLD", confidence=0.0, reason="warmup — indicators not ready")

            # BUY signal
            if current_rsi < self.rsi_oversold and current_close <= lower_band:
                entry = current_close * (1 - config.ENTRY_OFFSET_PCT)
                sl = entry - self.sl_mult * current_atr
                tp = entry + self.tp_mult * current_atr
                conf = min(1.0, (self.rsi_oversold - current_rsi) / self.rsi_oversold)
                return Signal(
                    action="BUY",
                    confidence=round(conf, 3),
                    reason=f"RSI={current_rsi:.1f}<{self.rsi_oversold} & close<=LBB",
                    entry_price=round(entry, 8),
                    sl_price=round(sl, 8),
                    tp_price=round(tp, 8),
                )

            return Signal(action="HOLD", confidence=0.0, reason=f"RSI={current_rsi:.1f} — no oversold")

        except Exception as exc:  # noqa: BLE001
            return Signal(action="HOLD", confidence=0.0, reason=f"error: {exc}")
