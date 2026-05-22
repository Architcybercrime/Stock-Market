# Indian markets guide

This system is configured by default for Indian equity markets (NSE) with a
fully-local paper broker. No broker account, no credit card, no MFA hoops —
the daemon runs and trades simulated INR positions using free yfinance data.

## What works today (no signup required)

- Daily-close paper trading on NSE Nifty 50 stocks
- Indian cost model: Zerodha-style brokerage cap (₹20), STT, stamp duty,
  exchange + SEBI charges, GST
- Indian market hours: scheduler fires after 15:30 IST close (10:00 UTC)
- State persists in `data/paper_state.json`, committed back to the repo by
  the GitHub Actions cron workflow
- Same three strategies as everything else: momentum, mean reversion,
  ML-driven (when models are trained)

## What real-money trading on Indian markets needs

You can paper-trade indefinitely with the current setup. Going to real money
requires an Indian broker integration. Comparison of the popular ones:

| Broker | API cost | KYC time | Algo-trading friendly | Paper trading on broker side |
|---|---|---|---|---|
| **Zerodha Kite Connect** | ₹2000/mo (~$24/mo) | 1–3 days | Best — established API, big community | "Sandbox" mode exists but limited |
| **Upstox** | Free | 1–3 days | Good, growing community | Yes, full paper trading API |
| **Angel One SmartAPI** | Free | 1–3 days | Decent, less polished | Yes |
| **Fyers** | Free | 1–3 days | Good for derivatives + equity | Yes |
| **5paisa** | Free | 1–3 days | OK | Yes |
| **Finvasia (Shoonya)** | Free | 1–3 days | OK, less docs | Limited |

**Recommendation when you're ready to go live:** Zerodha is the standard,
Upstox is a free alternative. For learning + early small-capital trading,
**Upstox is the better starting point** — free API, decent docs, you can
flip back to paper anytime.

None of these are wired up in this scaffold yet. When you're ready (60+ days
of paper-trading evidence), I can build an `UpstoxBroker` or `ZerodhaBroker`
that drops into the same `Broker` interface as `LocalPaperBroker` and
`AlpacaBroker`.

## KYC for any Indian broker

You'll need:

- **PAN card** (mandatory — Permanent Account Number from Income Tax)
- **Aadhaar card** (mandatory — government ID for e-sign)
- **Bank account** linked to that PAN
- **Active mobile number** linked to that Aadhaar (for OTP)
- A clear photo / scan of your signature
- Sometimes income proof (bank statement, salary slip) for derivatives access

The process is e-KYC + video verification, usually completed within 1–3
business days. There's no in-person visit needed for most brokers anymore.

## SEBI rules on retail algo trading

As of 2024–2026, the relevant points:

- **Personal use is fine.** You can write code that places orders on your own
  account. No registration needed.
- **You may not redistribute signals or offer it as a service** without
  registering as a Research Analyst or Investment Adviser. Don't sell signals.
- **All orders must go through the broker's API** and are subject to broker
  pre-trade checks (this scaffold also enforces pre-trade risk checks of its
  own).
- **For F&O (derivatives), brokers may apply additional risk limits** that
  our software can't override.

SEBI has periodically discussed tighter retail-algo rules. Check SEBI
circulars before going live; rules can change.

## Indian trading costs (what the cost model uses)

For DELIVERY (CNC) trades — held overnight, which is what the daily-close
daemon does — the rough breakdown:

```
Per ₹1 lakh traded:

Buy side:
  Brokerage   :  ₹20.00  (or 0.03%, whichever lower — ₹20 cap usually)
  Stamp duty  :  ₹15.00  (0.015%)
  Exchange    :   ₹3.22  (0.00322% NSE)
  SEBI        :   ₹0.10  (0.0001%)
  GST (18%)   :   ₹4.18  (on brokerage + exchange)
  ──────────────────────
  Buy total   :  ₹42.50  (~0.0425%)

Sell side:
  Brokerage   :  ₹20.00  (or 0.03%, whichever lower)
  STT         : ₹100.00  (0.1%)
  Exchange    :   ₹3.22  (0.00322%)
  SEBI        :   ₹0.10  (0.0001%)
  GST (18%)   :   ₹4.18  (on brokerage + exchange)
  ──────────────────────
  Sell total  : ₹127.50  (~0.1275%)

Round trip total: ~₹170 per ₹1 lakh, or ~0.17%
```

The `IndianEquityCostModel` in `services/backtest/costs.py` matches this
within a few basis points. The backtester and LocalPaperBroker both use it
by default on NSE/BSE.

**Implication:** Your strategy needs to generate at least ~0.17% per
round-trip just to break even. Daily turnover is expensive; weekly to monthly
holding periods are much friendlier to net P&L. The default risk profiles
have rebalance thresholds tuned for this.

## Indian market hours

| Session | IST | UTC |
|---|---|---|
| Pre-open | 09:00 – 09:15 | 03:30 – 03:45 |
| Regular | 09:15 – 15:30 | 03:45 – 10:00 |
| Post-close | 15:40 – 16:00 | 10:10 – 10:30 |

India does NOT observe daylight saving, so UTC times are fixed year-round.

The daemon fires at **10:30 UTC** = **16:00 IST** = 30 min after close,
giving the print plenty of time to settle.

## Universe

The default NSE universe in `scripts/run_daemon.py` is a diversified subset
of Nifty 50:

- **Banks**: HDFCBANK, ICICIBANK, KOTAKBANK, AXISBANK, SBIN
- **IT**: TCS, INFY, WIPRO, HCLTECH
- **Energy/Materials**: RELIANCE, ONGC, TATASTEEL
- **Auto**: MARUTI, TATAMOTORS, M&M
- **Consumer**: HINDUNILVR, ITC, ASIANPAINT, NESTLEIND
- **Pharma**: SUNPHARMA, DRREDDY
- **Telecom**: BHARTIARTL
- **Cement/Infra**: ULTRACEMCO, LT
- **NBFC/Insurance**: BAJFINANCE, BAJAJFINSV
- **ETFs**: NIFTYBEES (Nifty 50), BANKBEES (Bank Nifty)

To change: edit `NSE_UNIVERSE` in `scripts/run_daemon.py`, or pass
`--universe RELIANCE.NS TCS.NS INFY.NS` at the command line, or set the
`universe` input on a manual workflow run.

Always use the `.NS` suffix for NSE or `.BO` for BSE when querying yfinance.

## Running it locally

```bash
# Install deps (one time)
pip install -e ".[dev]"

# Smoke-test one cycle. No accounts, no keys needed.
python scripts/run_daemon.py --run-once --profile conservative

# See the simulated portfolio after
python scripts/show_portfolio.py --currency INR
```

## Running it on GitHub Actions (cron, free, no card)

Same as the US deploy but configured for NSE. See
[DEPLOY_GITHUB_ACTIONS.md](DEPLOY_GITHUB_ACTIONS.md) — the only India-specific
changes already baked in are:

- Cron fires at 10:30 UTC (after NSE close), not 21:30 UTC
- Default `--market NSE`, default `--broker local`
- No Alpaca secrets needed — they're optional and unused for Indian markets

You don't need to add any secrets to the repo. Just enable Actions and
trigger a manual run from the Actions tab to start.

## Realistic expectations

The [REALISTIC_EXPECTATIONS.md](REALISTIC_EXPECTATIONS.md) numbers apply to
Indian markets too, with one wrinkle: **Indian costs are roughly 4× the US
equivalent** (0.17% round-trip vs 0.04% on a commission-free US broker).
That makes high-turnover strategies meaningfully harder.

Counter-balancing: **Indian small/mid-caps historically show stronger
momentum** than US large-caps (less institutional efficiency, more retail
flow), so momentum strategies can work. But also more volatile and more
prone to flash drawdowns. Be careful sizing.

## Open work for future me (or future you)

- **UpstoxBroker** implementation (so live trading is one config switch
  after KYC is done)
- **ZerodhaBroker** as an alternative
- **F&O support** (currently equity-only; Indian retail trades a lot of
  weekly options, which is a different cost+risk profile)
- **NSE-specific data adapters** — Upstox and Zerodha both have free
  real-time WebSocket feeds for tick data, which would let the daemon run
  intraday strategies rather than only daily-close
- **STT-aware rebalancing** — current logic doesn't optimize for tax;
  add lot-level FIFO tracking so we don't trigger STT on lots we'd rather
  hold past the LTCG window
