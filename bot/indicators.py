"""
Pure-Python technical indicators.
All functions accept a list of floats (or Candle dicts) and return
a list of the same length — warmup positions are filled with None.
No external dependencies.
"""
from __future__ import annotations
from typing import List, Optional


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _closes(candles: List[dict]) -> List[float]:
    return [float(c["close"]) for c in candles]

def _highs(candles: List[dict]) -> List[float]:
    return [float(c["high"]) for c in candles]

def _lows(candles: List[dict]) -> List[float]:
    return [float(c["low"]) for c in candles]

def _volumes(candles: List[dict]) -> List[float]:
    return [float(c["volume"]) for c in candles]


# ---------------------------------------------------------------------------
# Simple Moving Average
# ---------------------------------------------------------------------------

def sma(values: List[float], period: int) -> List[Optional[float]]:
    result: List[Optional[float]] = [None] * len(values)
    for i in range(period - 1, len(values)):
        result[i] = sum(values[i - period + 1 : i + 1]) / period
    return result


# ---------------------------------------------------------------------------
# Exponential Moving Average
# ---------------------------------------------------------------------------

def ema(values: List[float], period: int) -> List[Optional[float]]:
    result: List[Optional[float]] = [None] * len(values)
    if len(values) < period:
        return result
    k = 2.0 / (period + 1)
    # Seed with SMA of first `period` values
    seed = sum(values[:period]) / period
    result[period - 1] = seed
    prev = seed
    for i in range(period, len(values)):
        curr = values[i] * k + prev * (1 - k)
        result[i] = curr
        prev = curr
    return result


# ---------------------------------------------------------------------------
# RSI (Wilder's smoothed method)
# ---------------------------------------------------------------------------

def rsi(values: List[float], period: int = 14) -> List[Optional[float]]:
    result: List[Optional[float]] = [None] * len(values)
    if len(values) < period + 1:
        return result

    gains, losses = [], []
    for i in range(1, len(values)):
        delta = values[i] - values[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))

    # First average (simple)
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    idx = period  # maps to values[period]

    def _rsi_val(ag: float, al: float) -> float:
        if al == 0:
            return 100.0
        rs = ag / al
        return 100.0 - (100.0 / (1 + rs))

    result[idx] = _rsi_val(avg_gain, avg_loss)

    for i in range(1, len(gains) - period + 1):
        avg_gain = (avg_gain * (period - 1) + gains[period + i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[period + i - 1]) / period
        result[idx + i] = _rsi_val(avg_gain, avg_loss)

    return result


# ---------------------------------------------------------------------------
# MACD
# ---------------------------------------------------------------------------

def macd(
    values: List[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> dict:
    """
    Returns dict with keys:
      'macd_line'   : List[Optional[float]]
      'signal_line' : List[Optional[float]]
      'histogram'   : List[Optional[float]]
    """
    n = len(values)
    ema_fast = ema(values, fast)
    ema_slow = ema(values, slow)

    macd_line: List[Optional[float]] = [None] * n
    for i in range(n):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            macd_line[i] = ema_fast[i] - ema_slow[i]  # type: ignore[operator]

    # Signal = EMA of macd_line values (non-None only)
    # Build a temporary list for EMA calculation
    macd_vals_only = [v for v in macd_line if v is not None]
    first_valid = next((i for i, v in enumerate(macd_line) if v is not None), None)

    signal_line: List[Optional[float]] = [None] * n
    histogram: List[Optional[float]] = [None] * n

    if first_valid is None or len(macd_vals_only) < signal:
        return {"macd_line": macd_line, "signal_line": signal_line, "histogram": histogram}

    sig_ema = ema(macd_vals_only, signal)
    # Map back
    offset = first_valid
    for j, v in enumerate(sig_ema):
        if v is not None:
            signal_line[offset + j] = v
            if macd_line[offset + j] is not None:
                histogram[offset + j] = macd_line[offset + j] - v  # type: ignore[operator]

    return {"macd_line": macd_line, "signal_line": signal_line, "histogram": histogram}


# ---------------------------------------------------------------------------
# Bollinger Bands
# ---------------------------------------------------------------------------

def bollinger(
    values: List[float], period: int = 20, num_std: float = 2.0
) -> dict:
    """
    Returns dict: 'upper', 'middle', 'lower' — each List[Optional[float]]
    """
    n = len(values)
    middle = sma(values, period)
    upper: List[Optional[float]] = [None] * n
    lower: List[Optional[float]] = [None] * n

    for i in range(period - 1, n):
        window = values[i - period + 1 : i + 1]
        mean = middle[i]
        if mean is None:
            continue
        variance = sum((x - mean) ** 2 for x in window) / period
        std = variance ** 0.5
        upper[i] = mean + num_std * std
        lower[i] = mean - num_std * std

    return {"upper": upper, "middle": middle, "lower": lower}


# ---------------------------------------------------------------------------
# ATR (Wilder smoothing)
# ---------------------------------------------------------------------------

def atr(candles: List[dict], period: int = 14) -> List[Optional[float]]:
    n = len(candles)
    result: List[Optional[float]] = [None] * n
    if n < 2:
        return result

    trs: List[float] = []
    for i in range(1, n):
        h = float(candles[i]["high"])
        l = float(candles[i]["low"])
        pc = float(candles[i - 1]["close"])
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)

    if len(trs) < period:
        return result

    # Seed
    atr_val = sum(trs[:period]) / period
    result[period] = atr_val  # index period (trs[0] = candles[1])
    for i in range(period, len(trs)):
        atr_val = (atr_val * (period - 1) + trs[i]) / period
        result[i + 1] = atr_val

    return result


# ---------------------------------------------------------------------------
# Donchian Channel
# ---------------------------------------------------------------------------

def donchian(candles: List[dict], period: int = 20) -> dict:
    """
    Returns dict: 'upper' (highest high), 'lower' (lowest low)
    """
    n = len(candles)
    upper: List[Optional[float]] = [None] * n
    lower: List[Optional[float]] = [None] * n

    for i in range(period - 1, n):
        window = candles[i - period + 1 : i + 1]
        upper[i] = max(float(c["high"]) for c in window)
        lower[i] = min(float(c["low"]) for c in window)

    return {"upper": upper, "lower": lower}


# ---------------------------------------------------------------------------
# ADX (Average Directional Index)
# ---------------------------------------------------------------------------

def adx(candles: List[dict], period: int = 14) -> List[Optional[float]]:
    """
    Returns smoothed ADX values, length == len(candles).
    Warmup positions are None.
    """
    n = len(candles)
    result: List[Optional[float]] = [None] * n
    if n < period * 2 + 1:
        return result

    plus_dm_list: List[float] = []
    minus_dm_list: List[float] = []
    tr_list: List[float] = []

    for i in range(1, n):
        h = float(candles[i]["high"])
        l = float(candles[i]["low"])
        ph = float(candles[i - 1]["high"])
        pl = float(candles[i - 1]["low"])
        pc = float(candles[i - 1]["close"])

        up_move = h - ph
        down_move = pl - l

        plus_dm = up_move if up_move > down_move and up_move > 0 else 0.0
        minus_dm = down_move if down_move > up_move and down_move > 0 else 0.0

        tr = max(h - l, abs(h - pc), abs(l - pc))
        plus_dm_list.append(plus_dm)
        minus_dm_list.append(minus_dm)
        tr_list.append(tr)

    # Wilder smoothing seed (sum of first `period` values)
    sm_tr = sum(tr_list[:period])
    sm_plus = sum(plus_dm_list[:period])
    sm_minus = sum(minus_dm_list[:period])

    def _dx(sp: float, sm: float, st: float) -> Optional[float]:
        if st == 0:
            return None
        pdi = 100 * sp / st
        mdi = 100 * sm / st
        denom = pdi + mdi
        if denom == 0:
            return 0.0
        return 100 * abs(pdi - mdi) / denom

    dx_list: List[Optional[float]] = []
    dx_list.append(_dx(sm_plus, sm_minus, sm_tr))

    for i in range(period, len(tr_list)):
        sm_tr = sm_tr - sm_tr / period + tr_list[i]
        sm_plus = sm_plus - sm_plus / period + plus_dm_list[i]
        sm_minus = sm_minus - sm_minus / period + minus_dm_list[i]
        dx_list.append(_dx(sm_plus, sm_minus, sm_tr))

    # ADX = Wilder-smoothed DX
    valid_dx = [v for v in dx_list if v is not None]
    if len(valid_dx) < period:
        return result

    adx_val = sum(valid_dx[:period]) / period
    # Map adx_val back — first ADX sits at candles index = period*2
    base_idx = period * 2
    if base_idx < n:
        result[base_idx] = adx_val

    for i in range(period, len(valid_dx)):
        adx_val = (adx_val * (period - 1) + valid_dx[i]) / period
        idx = base_idx + (i - period + 1)
        if idx < n:
            result[idx] = adx_val

    return result


# ---------------------------------------------------------------------------
# Volume SMA helper (used by breakout strategy)
# ---------------------------------------------------------------------------

def volume_sma(candles: List[dict], period: int = 20) -> List[Optional[float]]:
    vols = _volumes(candles)
    return sma(vols, period)
