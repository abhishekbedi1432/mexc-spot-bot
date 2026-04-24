# Binance $10 Spot Trading Bot

A minimal, auditable Python spot-trading bot for Binance.
- Runs every 5 minutes via GitHub Actions (zero infra cost on public repos)
- $10 USDT starting capital · strict paper-first rollout
- Multi-strategy pack (mean reversion, trend EMA, breakout, momentum)
- Per-pair strategy chosen by walk-forward backtest — not hand-picked
- `DRY_RUN=true` by default — **never trades real money until you flip the flag**

---

## Quick Start

```bash
git clone https://github.com/abhishekbedi1432/mexc-spot-bot.git
cd mexc-spot-bot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your keys
pytest tests/ -v       # all 36 tests must pass
python3 -m bot.main    # single dry-run tick
```

---

## Project Layout

```
bot/
  config.py            # pair universe, risk params, env loader
  binance_client.py    # HMAC-SHA256 signed HTTP client
  indicators.py        # pure-Python RSI/EMA/MACD/BB/ATR/Donchian/ADX
  risk.py              # sizing, spread guard, daily kill-switch
  executor.py          # LIMIT order placement
  backtester.py        # walk-forward simulator (Phase 2)
  paper_trader.py      # simulated fills (Phase 4)
  main.py              # 5-min orchestrator
  strategies/
    base.py            # Signal dataclass + Strategy interface
    mean_reversion.py  # RSI + Bollinger Bands
    trend_ema.py       # EMA 9/21 cross + ADX filter
    breakout_donchian.py # 20-bar high + volume spike
    momentum_macd.py   # MACD histogram flip + RSI > 50
scripts/
  run_backtest.py      # backtest all strategies × all pairs
  pick_strategy.py     # write config/chosen_strategies.json
tests/
  test_indicators.py   # 36 unit tests, no network
config/
  chosen_strategies.json  # auto-written by pick_strategy.py
logs/
  decisions.jsonl      # committed each run (audit heartbeat)
.github/workflows/
  trade.yml            # 5-min cron + tests guard
```

---

## Rollout Phases

| Phase | What | Status |
|-------|------|--------|
| 0 | Scaffold + indicator tests | ✅ Done |
| 1 | Data layer — fetch 30d klines | Next |
| 2 | Backtester — leaderboard + strategy selection | Pending |
| 3 | GitHub Actions wiring | Pending |
| 4 | Forward paper trading (5–7 days) | Pending |
| 5 | Authed read — account + open orders | Pending |
| 6 | Live $2–3/trade, single best pair | Pending |
| 7 | Scale to $5/trade, add second pair | Pending |
| 8 | Telegram notifications | Pending |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BINANCE_API_KEY` | — | Read-only key for Phases 0–4; add TRADE permission for Phase 5+ |
| `BINANCE_API_SECRET` | — | Keep secret — never commit |
| `DRY_RUN` | `true` | Set `false` only for Phase 6+ live trading |
| `CAPITAL_USDT` | `10.0` | Starting capital |

---

## API Key Setup (Binance)

1. Profile → API Management → **Create API** → **System generated**
2. Name: `claude-trading-bot`
3. **Phases 0–4 (read-only):** Enable Reading only. Leave all other permissions OFF. IP: Unrestricted.
4. **Phase 5+ (live):** Enable Reading + Spot & Margin Trading. **Never enable Withdrawals.** Whitelist your VPS static IP.
5. Store keys in GitHub Actions secrets: `BINANCE_API_KEY`, `BINANCE_API_SECRET`

> ⚠️ Binance auto-deletes unrestricted keys that have TRADE permission enabled.
> You must whitelist a static IP before enabling trade permission.

---

## Deployment

**Phases 0–4 (no credentials needed for paper):** GitHub Actions — free forever on public repos.

**Phase 5+ (live TRADE permission):**
- Oracle Cloud Always Free VM (AMD or ARM, free forever) — recommended
- Hetzner CX22 (~€4.51/mo) — best paid option
- Any Linux server with a static public IPv4

---

## Risk Rails (hard-coded, non-overridable)

- Max 1 open position at any time
- Per-trade notional = `min($9, capital × 90%)`
- Daily loss kill-switch at **−5%** of start-of-day equity
- SL = 1× ATR(14), TP = 1.5× ATR → RR ≈ 1:1.5
- Skip if spread > 0.05% or expected profit < 2× round-trip fees
- `DRY_RUN=true` default — never live unless explicitly set

---

## Honest Reality Check

With $10 capital and 0.20% round-trip fees, this bot is a **discipline and learning harness**, not a money printer.
Success metric = zero blow-ups + clean execution + positive edge confirmed by backtest.

---

*Co-Authored-By: Oz <oz-agent@warp.dev>*
