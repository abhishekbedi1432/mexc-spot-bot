"""
Unit tests for bot/indicators.py
All tests use deterministic fixture data — no network calls.
"""
import pytest
from bot import indicators as ind


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_candles(closes, highs=None, lows=None, volumes=None):
    """Build minimal candle dicts from lists."""
    n = len(closes)
    highs = highs or [c * 1.01 for c in closes]
    lows = lows or [c * 0.99 for c in closes]
    volumes = volumes or [1000.0] * n
    return [
        {"open": closes[i], "high": highs[i], "low": lows[i],
         "close": closes[i], "volume": volumes[i]}
        for i in range(n)
    ]


# Arithmetic sequence 1..30 — simple to verify manually
CLOSES_30 = list(range(1, 31))  # [1, 2, ..., 30]
CANDLES_30 = make_candles(CLOSES_30)

# Constant series — RSI of all-up moves should be 100
CLOSES_UP = [10.0 + i * 0.1 for i in range(30)]
CLOSES_DOWN = [20.0 - i * 0.1 for i in range(30)]


# ---------------------------------------------------------------------------
# SMA
# ---------------------------------------------------------------------------

class TestSMA:
    def test_length_preserved(self):
        result = ind.sma(CLOSES_30, 5)
        assert len(result) == 30

    def test_warmup_is_none(self):
        result = ind.sma(CLOSES_30, 5)
        for i in range(4):
            assert result[i] is None

    def test_first_valid_value(self):
        # SMA(5) at index 4 = mean of [1,2,3,4,5] = 3.0
        result = ind.sma(CLOSES_30, 5)
        assert result[4] == pytest.approx(3.0)

    def test_last_value(self):
        # SMA(5) at index 29 = mean of [26,27,28,29,30] = 28.0
        result = ind.sma(CLOSES_30, 5)
        assert result[29] == pytest.approx(28.0)

    def test_period_1(self):
        result = ind.sma(CLOSES_30, 1)
        assert result == pytest.approx(CLOSES_30)

    def test_too_short(self):
        result = ind.sma([1.0, 2.0], 5)
        assert all(v is None for v in result)


# ---------------------------------------------------------------------------
# EMA
# ---------------------------------------------------------------------------

class TestEMA:
    def test_length_preserved(self):
        result = ind.ema(CLOSES_30, 5)
        assert len(result) == 30

    def test_warmup_is_none(self):
        result = ind.ema(CLOSES_30, 5)
        for i in range(4):
            assert result[i] is None

    def test_seed_equals_sma(self):
        # EMA seed at index period-1 should equal SMA of first `period` values
        period = 5
        ema_vals = ind.ema(CLOSES_30, period)
        sma_vals = ind.sma(CLOSES_30, period)
        assert ema_vals[period - 1] == pytest.approx(sma_vals[period - 1])

    def test_monotone_increasing(self):
        # For strictly increasing input, EMA should also be increasing (after warmup)
        result = ind.ema(CLOSES_UP, 5)
        valid = [v for v in result if v is not None]
        assert all(valid[i] < valid[i + 1] for i in range(len(valid) - 1))

    def test_period_equals_length(self):
        closes = [1.0, 2.0, 3.0]
        result = ind.ema(closes, 3)
        assert result[0] is None
        assert result[1] is None
        assert result[2] == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# RSI
# ---------------------------------------------------------------------------

class TestRSI:
    def test_length_preserved(self):
        result = ind.rsi(CLOSES_30, 14)
        assert len(result) == 30

    def test_warmup_is_none(self):
        result = ind.rsi(CLOSES_30, 14)
        # First valid at index 14
        for i in range(14):
            assert result[i] is None

    def test_all_up_gives_100(self):
        result = ind.rsi(CLOSES_UP, 14)
        valid = [v for v in result if v is not None]
        for v in valid:
            assert v == pytest.approx(100.0)

    def test_all_down_gives_0(self):
        result = ind.rsi(CLOSES_DOWN, 14)
        valid = [v for v in result if v is not None]
        for v in valid:
            assert v == pytest.approx(0.0)

    def test_range_0_to_100(self):
        import random
        random.seed(42)
        closes = [10.0 + random.uniform(-1, 1) for _ in range(50)]
        result = ind.rsi(closes, 14)
        for v in result:
            if v is not None:
                assert 0.0 <= v <= 100.0


# ---------------------------------------------------------------------------
# MACD
# ---------------------------------------------------------------------------

class TestMACD:
    def test_keys_present(self):
        result = ind.macd(CLOSES_30)
        assert "macd_line" in result
        assert "signal_line" in result
        assert "histogram" in result

    def test_lengths_preserved(self):
        result = ind.macd(CLOSES_30)
        assert len(result["macd_line"]) == 30
        assert len(result["signal_line"]) == 30
        assert len(result["histogram"]) == 30

    def test_histogram_equals_macd_minus_signal(self):
        result = ind.macd(CLOSES_30, 3, 6, 3)
        for i in range(30):
            ml = result["macd_line"][i]
            sl = result["signal_line"][i]
            h = result["histogram"][i]
            if ml is not None and sl is not None and h is not None:
                assert h == pytest.approx(ml - sl, abs=1e-10)

    def test_too_short_returns_all_none(self):
        result = ind.macd([1.0, 2.0, 3.0])
        assert all(v is None for v in result["macd_line"])


# ---------------------------------------------------------------------------
# Bollinger Bands
# ---------------------------------------------------------------------------

class TestBollinger:
    def test_keys_present(self):
        result = ind.bollinger(CLOSES_30)
        assert "upper" in result and "middle" in result and "lower" in result

    def test_lengths_preserved(self):
        result = ind.bollinger(CLOSES_30, 5)
        assert len(result["upper"]) == 30

    def test_upper_gt_middle_gt_lower(self):
        result = ind.bollinger(CLOSES_30, 5)
        for i in range(30):
            u, m, l = result["upper"][i], result["middle"][i], result["lower"][i]
            if all(v is not None for v in [u, m, l]):
                assert u >= m >= l

    def test_constant_series_zero_bandwidth(self):
        # Constant closes → std=0 → upper == middle == lower
        closes = [5.0] * 25
        result = ind.bollinger(closes, 5)
        for i in range(4, 25):
            assert result["upper"][i] == pytest.approx(5.0)
            assert result["lower"][i] == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# ATR
# ---------------------------------------------------------------------------

class TestATR:
    def test_length_preserved(self):
        result = ind.atr(CANDLES_30, 14)
        assert len(result) == 30

    def test_warmup_is_none(self):
        result = ind.atr(CANDLES_30, 14)
        for i in range(14):
            assert result[i] is None

    def test_atr_positive(self):
        result = ind.atr(CANDLES_30, 5)
        valid = [v for v in result if v is not None]
        assert all(v > 0 for v in valid)

    def test_zero_range_candles(self):
        # All candles identical → ATR should be tiny (previous close = current close)
        candles = [{"open": 10.0, "high": 10.0, "low": 10.0,
                    "close": 10.0, "volume": 100.0}] * 20
        result = ind.atr(candles, 5)
        valid = [v for v in result if v is not None]
        for v in valid:
            assert v == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# Donchian
# ---------------------------------------------------------------------------

class TestDonchian:
    def test_keys_present(self):
        result = ind.donchian(CANDLES_30)
        assert "upper" in result and "lower" in result

    def test_lengths_preserved(self):
        result = ind.donchian(CANDLES_30, 5)
        assert len(result["upper"]) == 30

    def test_warmup_is_none(self):
        result = ind.donchian(CANDLES_30, 5)
        for i in range(4):
            assert result["upper"][i] is None

    def test_upper_gte_lower(self):
        result = ind.donchian(CANDLES_30, 5)
        for i in range(30):
            u, l = result["upper"][i], result["lower"][i]
            if u is not None and l is not None:
                assert u >= l

    def test_known_values(self):
        # highs 1..30, lows 0..29 — Donchian(5) at index 4:
        # upper = max highs[0..4], lower = min lows[0..4]
        closes = list(range(1, 31))
        highs = [c + 1 for c in closes]
        lows = [c - 1 for c in closes]
        candles = make_candles(closes, highs, lows)
        result = ind.donchian(candles, 5)
        # At index 4: highs window = [2,3,4,5,6] → max=6; lows = [0,1,2,3,4] → min=0
        assert result["upper"][4] == pytest.approx(6.0)
        assert result["lower"][4] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# ADX
# ---------------------------------------------------------------------------

class TestADX:
    def test_length_preserved(self):
        result = ind.adx(CANDLES_30, 5)
        assert len(result) == 30

    def test_range_0_to_100(self):
        result = ind.adx(CANDLES_30, 5)
        for v in result:
            if v is not None:
                assert 0.0 <= v <= 100.0

    def test_strong_trend_high_adx(self):
        # Strong uptrend — all candles moving up with consistent direction
        closes = [10.0 + i * 0.5 for i in range(60)]
        highs = [c + 0.3 for c in closes]
        lows = [c - 0.1 for c in closes]
        candles = make_candles(closes, highs, lows)
        result = ind.adx(candles, 14)
        valid = [v for v in result if v is not None]
        assert len(valid) > 0
        # ADX should be non-trivially high in a strong trend
        assert max(valid) > 20.0
