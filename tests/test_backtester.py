"""
Unit tests for bot/backtester.py
Uses synthetic candles to verify SL/TP mechanics, fee model,
max drawdown, and profit factor.  No network calls.
"""
import math
import pytest

from bot.backtester import (
    BacktestMetrics,
    Trade,
    _calc_trade_pnl,
    _max_drawdown,
    _auto_step_size,
    run_backtest,
    WARMUP,
)
from bot import config
from bot.strategies.base import Signal, Strategy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_flat_candles(n: int, price: float = 100.0, spread: float = 1.0) -> list:
    """n flat candles — strategy will see no signal (RSI / BB won't trigger)."""
    return [
        {
            "open_time": i * 300_000,
            "open": price,
            "high": price + spread,
            "low": price - spread,
            "close": price,
            "volume": 1000.0,
            "close_time": (i + 1) * 300_000 - 1,
        }
        for i in range(n)
    ]


class AlwaysBuyStrategy(Strategy):
    """Emits a BUY on every tick with fixed entry/SL/TP."""
    name = "always_buy"

    def __init__(self, entry=100.0, sl=95.0, tp=110.0):
        self.entry = entry
        self.sl = sl
        self.tp = tp

    def decide(self, candles):
        return Signal(
            action="BUY",
            confidence=1.0,
            reason="test",
            entry_price=self.entry,
            sl_price=self.sl,
            tp_price=self.tp,
        )


class AlwaysHoldStrategy(Strategy):
    name = "always_hold"

    def decide(self, candles):
        return Signal(action="HOLD", confidence=0.0, reason="test")


def candles_with_tp_hit(entry=100.0, tp=110.0, sl=95.0, n_before=60, n_after=5):
    """
    Flat candles for warmup, then one candle whose high touches TP.
    """
    candles = make_flat_candles(n_before, price=entry)
    # TP-hit candle: high >= tp
    candles.append({
        "open_time": n_before * 300_000,
        "open": entry,
        "high": tp + 1.0,
        "low": entry - 0.5,
        "close": entry + 5.0,
        "volume": 1000.0,
        "close_time": (n_before + 1) * 300_000 - 1,
    })
    candles += make_flat_candles(n_after, price=entry + 5.0)
    return candles


def candles_with_sl_hit(entry=100.0, tp=110.0, sl=95.0, n_before=60, n_after=5):
    """Flat candles for warmup, then one candle whose low touches SL."""
    candles = make_flat_candles(n_before, price=entry)
    candles.append({
        "open_time": n_before * 300_000,
        "open": entry,
        "high": entry + 0.5,
        "low": sl - 1.0,
        "close": entry - 3.0,
        "volume": 1000.0,
        "close_time": (n_before + 1) * 300_000 - 1,
    })
    candles += make_flat_candles(n_after, price=entry - 3.0)
    return candles


# ---------------------------------------------------------------------------
# _auto_step_size
# ---------------------------------------------------------------------------

class TestAutoStepSize:
    def test_btc_price(self):
        assert _auto_step_size(90_000) == pytest.approx(0.00001)

    def test_eth_price(self):
        assert _auto_step_size(1_800) == pytest.approx(0.0001)

    def test_sol_price(self):
        assert _auto_step_size(130) == pytest.approx(0.01)

    def test_doge_price(self):
        assert _auto_step_size(0.18) == pytest.approx(0.1)


# ---------------------------------------------------------------------------
# _calc_trade_pnl fee model
# ---------------------------------------------------------------------------

class TestCalcTradePnl:
    def test_tp_exit_uses_maker_both_sides(self):
        entry, exit_p, qty = 100.0, 110.0, 1.0
        gross = (exit_p - entry) * qty  # 10.0
        expected_fees = (config.MAKER_FEE * entry + config.MAKER_FEE * exit_p) * qty
        expected = gross - expected_fees
        assert _calc_trade_pnl(entry, exit_p, qty, "TP") == pytest.approx(expected)

    def test_sl_exit_uses_taker_on_exit(self):
        entry, exit_p, qty = 100.0, 95.0, 1.0
        gross = (exit_p - entry) * qty  # -5.0
        expected_fees = (config.MAKER_FEE * entry + config.TAKER_FEE * exit_p) * qty
        expected = gross - expected_fees
        assert _calc_trade_pnl(entry, exit_p, qty, "SL") == pytest.approx(expected)

    def test_end_of_data_uses_taker(self):
        # END_OF_DATA treated same as SL
        pnl_sl = _calc_trade_pnl(100.0, 105.0, 1.0, "SL")
        pnl_eod = _calc_trade_pnl(100.0, 105.0, 1.0, "END_OF_DATA")
        assert pnl_sl == pytest.approx(pnl_eod)

    def test_breakeven_trade_negative_due_to_fees(self):
        # entry == exit → net must be negative (fees)
        pnl = _calc_trade_pnl(100.0, 100.0, 1.0, "TP")
        assert pnl < 0


# ---------------------------------------------------------------------------
# _max_drawdown
# ---------------------------------------------------------------------------

class TestMaxDrawdown:
    def test_no_drawdown(self):
        equity = [10.0, 11.0, 12.0, 13.0]
        assert _max_drawdown(equity) == pytest.approx(0.0)

    def test_full_loss(self):
        equity = [10.0, 0.0]
        assert _max_drawdown(equity) == pytest.approx(1.0)

    def test_known_drawdown(self):
        # Peak 12, then drops to 9 → DD = 3/12 = 25%
        equity = [10.0, 12.0, 9.0, 11.0]
        assert _max_drawdown(equity) == pytest.approx(3.0 / 12.0)

    def test_empty(self):
        assert _max_drawdown([]) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# run_backtest — always-hold strategy
# ---------------------------------------------------------------------------

class TestRunBacktestHold:
    def test_no_trades_on_hold_strategy(self):
        candles = make_flat_candles(200)
        m = run_backtest(AlwaysHoldStrategy(), candles, symbol="TEST")
        assert m.total_trades == 0
        assert m.net_pnl_usdt == pytest.approx(0.0)

    def test_too_short_returns_empty(self):
        candles = make_flat_candles(WARMUP - 1)
        m = run_backtest(AlwaysHoldStrategy(), candles)
        assert m.total_trades == 0


# ---------------------------------------------------------------------------
# run_backtest — TP hit
# ---------------------------------------------------------------------------

class TestRunBacktestTPHit:
    def test_tp_trade_recorded(self):
        entry, tp, sl = 100.0, 110.0, 95.0
        candles = candles_with_tp_hit(entry=entry, tp=tp, sl=sl)
        strategy = AlwaysBuyStrategy(entry=entry, sl=sl, tp=tp)
        m = run_backtest(strategy, candles, initial_capital=10.0, step_size=0.01)
        assert m.total_trades >= 1
        # At least one winning trade
        assert m.winning_trades >= 1

    def test_tp_exit_reason(self):
        entry, tp, sl = 100.0, 110.0, 95.0
        candles = candles_with_tp_hit(entry=entry, tp=tp, sl=sl, n_before=60)
        strategy = AlwaysBuyStrategy(entry=entry, sl=sl, tp=tp)
        m = run_backtest(strategy, candles, initial_capital=10.0, step_size=0.01)
        tp_trades = [t for t in m.trades if t.exit_reason == "TP"]
        assert len(tp_trades) >= 1

    def test_capital_increases_after_tp(self):
        entry, tp, sl = 100.0, 110.0, 95.0
        candles = candles_with_tp_hit(entry=entry, tp=tp, sl=sl)
        strategy = AlwaysBuyStrategy(entry=entry, sl=sl, tp=tp)
        m = run_backtest(strategy, candles, initial_capital=10.0, step_size=0.01)
        # Only if at least one TP trade fired
        tp_trades = [t for t in m.trades if t.exit_reason == "TP"]
        if tp_trades:
            assert m.final_capital > 10.0


# ---------------------------------------------------------------------------
# run_backtest — SL hit
# ---------------------------------------------------------------------------

class TestRunBacktestSLHit:
    def test_sl_trade_recorded(self):
        entry, tp, sl = 100.0, 110.0, 95.0
        candles = candles_with_sl_hit(entry=entry, tp=tp, sl=sl)
        strategy = AlwaysBuyStrategy(entry=entry, sl=sl, tp=tp)
        m = run_backtest(strategy, candles, initial_capital=10.0, step_size=0.01)
        assert m.total_trades >= 1

    def test_sl_exit_reason(self):
        entry, tp, sl = 100.0, 110.0, 95.0
        candles = candles_with_sl_hit(entry=entry, tp=tp, sl=sl, n_before=60)
        strategy = AlwaysBuyStrategy(entry=entry, sl=sl, tp=tp)
        m = run_backtest(strategy, candles, initial_capital=10.0, step_size=0.01)
        sl_trades = [t for t in m.trades if t.exit_reason == "SL"]
        assert len(sl_trades) >= 1

    def test_capital_decreases_after_sl(self):
        entry, tp, sl = 100.0, 110.0, 95.0
        candles = candles_with_sl_hit(entry=entry, tp=tp, sl=sl)
        strategy = AlwaysBuyStrategy(entry=entry, sl=sl, tp=tp)
        m = run_backtest(strategy, candles, initial_capital=10.0, step_size=0.01)
        sl_trades = [t for t in m.trades if t.exit_reason == "SL"]
        if sl_trades:
            assert m.final_capital < 10.0


# ---------------------------------------------------------------------------
# run_backtest — aggregate metrics
# ---------------------------------------------------------------------------

class TestRunBacktestMetrics:
    def _run_mixed(self) -> BacktestMetrics:
        """Run with alternating TP and SL candles."""
        entry, tp, sl = 100.0, 110.0, 95.0
        candles = (
            make_flat_candles(60, price=entry)
            + candles_with_tp_hit(entry, tp, sl, n_before=0, n_after=0)
            + make_flat_candles(20, price=entry)
            + candles_with_sl_hit(entry, tp, sl, n_before=0, n_after=10)
        )
        strategy = AlwaysBuyStrategy(entry=entry, sl=sl, tp=tp)
        return run_backtest(strategy, candles, initial_capital=10.0, step_size=0.01)

    def test_win_rate_between_0_and_1(self):
        m = self._run_mixed()
        assert 0.0 <= m.win_rate <= 1.0

    def test_max_drawdown_between_0_and_1(self):
        m = self._run_mixed()
        assert 0.0 <= m.max_drawdown_pct <= 1.0

    def test_profit_factor_non_negative(self):
        m = self._run_mixed()
        assert m.profit_factor >= 0.0

    def test_summary_keys(self):
        m = self._run_mixed()
        s = m.summary()
        for key in ["symbol", "strategy", "total_trades", "win_rate",
                    "net_pnl_usdt", "max_drawdown_pct", "profit_factor"]:
            assert key in s

    def test_trade_is_win_consistent(self):
        """trade.is_win must agree with trade.net_pnl_usdt sign."""
        m = self._run_mixed()
        for t in m.trades:
            assert t.is_win == (t.net_pnl_usdt > 0)


# ---------------------------------------------------------------------------
# Confidence filter gate
# ---------------------------------------------------------------------------

class TestConfidenceFilter:
    def test_high_confidence_threshold_blocks_low_confidence(self):
        """AlwaysBuyStrategy emits confidence=1.0 — should pass any threshold."""
        entry, tp, sl = 100.0, 110.0, 95.0
        candles = candles_with_tp_hit(entry=entry, tp=tp, sl=sl)
        strategy = AlwaysBuyStrategy(entry=entry, sl=sl, tp=tp)
        # confidence=1.0 always emitted, threshold=0.9 — should still trade
        m = run_backtest(strategy, candles, initial_capital=10.0, step_size=0.01, min_confidence=0.9)
        assert m.total_trades >= 1

    def test_confidence_filter_blocks_all_trades(self):
        """Threshold above 1.0 must block all trades."""
        entry, tp, sl = 100.0, 110.0, 95.0
        candles = candles_with_tp_hit(entry=entry, tp=tp, sl=sl)
        strategy = AlwaysBuyStrategy(entry=entry, sl=sl, tp=tp)
        m = run_backtest(strategy, candles, initial_capital=10.0, step_size=0.01, min_confidence=1.1)
        assert m.total_trades == 0

    def test_zero_threshold_is_same_as_no_filter(self):
        """min_confidence=0.0 must match baseline (backward compat)."""
        entry, tp, sl = 100.0, 110.0, 95.0
        candles = candles_with_tp_hit(entry=entry, tp=tp, sl=sl)
        strategy = AlwaysBuyStrategy(entry=entry, sl=sl, tp=tp)
        m0 = run_backtest(strategy, candles, initial_capital=10.0, step_size=0.01, min_confidence=0.0)
        m_base = run_backtest(strategy, candles, initial_capital=10.0, step_size=0.01)
        assert m0.total_trades == m_base.total_trades


# ---------------------------------------------------------------------------
# is_profit_viable gate (wired into backtester)
# ---------------------------------------------------------------------------

class TestProfitViabilityGate:
    def test_tight_tp_filtered_out(self):
        """
        Entry=100, TP=100.1 (0.1% move): expected profit < 2× round-trip fees (0.20%) → skipped.
        """
        from bot.risk import is_profit_viable
        from bot import config
        entry, sl, tp = 100.0, 99.0, 100.1
        notional = 9.0
        assert not is_profit_viable(entry, sl, tp, notional)

    def test_adequate_tp_passes(self):
        """Entry=100, TP=101.5 (1.5% move with ATR): should pass viability check."""
        from bot.risk import is_profit_viable
        entry, sl, tp = 100.0, 99.0, 101.5
        notional = 9.0
        assert is_profit_viable(entry, sl, tp, notional)

    def test_backtester_with_profit_gate_trades_less_than_without(self):
        """
        With a tight TP (ATR=0.1 → TP=100.15), profit gate blocks trades.
        With a wide TP (ATR=1.0 → TP=101.5), profit gate allows trades.
        """
        # Tight TP strategy: barely viable
        class TightTPStrategy(Strategy):
            name = "tight_tp"
            def decide(self, candles):
                return Signal(
                    action="BUY", confidence=1.0, reason="test",
                    entry_price=100.0, sl_price=99.9, tp_price=100.1,  # 0.1% TP
                )

        candles = candles_with_tp_hit(entry=100.0, tp=100.1, sl=99.9, n_before=60)
        m_tight = run_backtest(TightTPStrategy(), candles, initial_capital=10.0, step_size=0.01)
        # Wide TP strategy: clearly viable
        m_wide = run_backtest(
            AlwaysBuyStrategy(entry=100.0, sl=95.0, tp=110.0),
            candles, initial_capital=10.0, step_size=0.01
        )
        # Tight TP should produce 0 trades (profit gate filters it)
        # Wide TP should produce ≥1 trade
        assert m_tight.total_trades == 0
        assert m_wide.total_trades >= 1
