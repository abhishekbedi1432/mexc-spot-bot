"""
Central configuration for the Binance $10 spot trading bot.
All sensitive values come from environment variables — never hard-coded.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
LOGS_DIR = ROOT / "logs"
CHOSEN_STRATEGIES_FILE = CONFIG_DIR / "chosen_strategies.json"

# ---------------------------------------------------------------------------
# Exchange
# ---------------------------------------------------------------------------
BASE_URL = "https://api.binance.com"
KLINE_INTERVAL = "5m"
KLINE_LIMIT = 150  # ~12.5 hours of 5-min candles — enough for all indicators

# ---------------------------------------------------------------------------
# Secrets (loaded from env — never committed)
# ---------------------------------------------------------------------------
API_KEY: str = os.getenv("BINANCE_API_KEY", "")
API_SECRET: str = os.getenv("BINANCE_API_SECRET", "")

# Master switch — True = paper-only, False = real orders
DRY_RUN: bool = os.getenv("DRY_RUN", "true").lower() != "false"

# ---------------------------------------------------------------------------
# Pair universe
# Filter: >= 5M USDT 24h volume, no native-token conflict
# ---------------------------------------------------------------------------
PAIRS: List[str] = [
    "BTCUSDT",   # ~$325M 24h vol
    "ETHUSDT",   # ~$143M 24h vol
    "SOLUSDT",   # ~$36M  24h vol
    "DOGEUSDT",  # ~$17M  24h vol
]

# Watchlist — not traded until backtest confirms edge
WATCHLIST: List[str] = ["SUIUSDT"]

# Excluded (documented reason)
# MXUSDT  — Binance-listed but structurally conflicts with exchange promos
# ETCUSDT, IMXUSDT, ILVUSDT — <100K 24h vol; spread eats $10 account

# ---------------------------------------------------------------------------
# Risk rails (hard-coded, non-overridable via env)
# ---------------------------------------------------------------------------
MAX_OPEN_POSITIONS: int = 1
CAPITAL_USDT: float = float(os.getenv("CAPITAL_USDT", "10.0"))

# Per-trade notional = min(MAX_TRADE_USDT, capital * CAPITAL_FRACTION)
MAX_TRADE_USDT: float = 9.0
CAPITAL_FRACTION: float = 0.90

# ATR multipliers for SL / TP
# Grid search (30d, 4 pairs × 4 strategies, min_confidence=0.3) confirmed:
# TP=1.5 is optimal — higher TP collapses win rate faster than RR improves.
# SL=1.25 gives best win rate (49%) and least-negative aggregate PnL.
SL_ATR_MULT: float = 1.25
TP_ATR_MULT: float = 1.5   # RR ≈ 1:1.2

# Daily loss kill-switch: if today's PnL <= this fraction of start-of-day equity → HOLD
DAILY_LOSS_LIMIT: float = -0.05  # -5%

# Order fill timeout in seconds before cancel
FILL_TIMEOUT_SECONDS: int = 60

# Entry LIMIT price offset below close (maker order; 0% fee)
ENTRY_OFFSET_PCT: float = 0.0005  # 0.05%

# Skip trade if spread > this
MAX_SPREAD_PCT: float = 0.0005  # 0.05%

# Skip trade if expected net profit < this multiple of round-trip fees.
# 3.0 = TP profit must be ≥ 3× round-trip cost. Ensures ATR/price ≥ ~0.4%.
MIN_PROFIT_FEE_MULTIPLE: float = 3.0

# Binance VIP 0 fees
MAKER_FEE: float = 0.001   # 0.10%
TAKER_FEE: float = 0.001   # 0.10%
ROUND_TRIP_FEE: float = MAKER_FEE + TAKER_FEE  # 0.20%

# Stale data guard: if last candle is older than this many seconds → HOLD
MAX_CANDLE_AGE_SECONDS: int = 360  # 2 missed 5-min candles

# Signal quality gate — skip BUY if confidence < this (0.0 = off, 0.3 = default filter)
# Calibration: mean_reversion→RSI depth, trend_ema→ADX/50, breakout→volume ratio, macd→RSI position
MIN_CONFIDENCE: float = float(os.getenv("MIN_CONFIDENCE", "0.3"))

# ---------------------------------------------------------------------------
# Chosen strategies (populated by scripts/pick_strategy.py after backtest)
# ---------------------------------------------------------------------------

def load_chosen_strategies() -> Dict[str, str]:
    """
    Returns mapping of {pair: strategy_name}.
    Falls back to empty dict if file not yet created (pre-Phase 2).
    """
    if not CHOSEN_STRATEGIES_FILE.exists():
        return {}
    with open(CHOSEN_STRATEGIES_FILE) as f:
        return json.load(f)


def save_chosen_strategies(mapping: Dict[str, str]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CHOSEN_STRATEGIES_FILE, "w") as f:
        json.dump(mapping, f, indent=2)
