# Stock_Market — Institutional AI Trading Platform

A production-oriented, modular AI trading platform. Defaults to **Indian
equity markets (NSE)** with Zerodha-style cost modelling. Built with capital
preservation first, risk-adjusted returns second, automation third.

**Live dashboard** (once Pages is enabled):
**https://architcybercrime.github.io/Stock-Market/**

The dashboard is a static page that reads `data/paper_state.json` directly
from this repo — refreshes whenever the daemon or snapshot workflow commits
new state. See [docs/DASHBOARD.md](docs/DASHBOARD.md) for the one-time
GitHub Pages enable step.

> **Status: scaffold.** Working foundation for *paper trading on real market
> data*. No real-money broker is wired up yet — that's deliberate. Read
> [docs/INDIA_GUIDE.md](docs/INDIA_GUIDE.md) for the Indian-market specifics
> and [docs/REALISTIC_EXPECTATIONS.md](docs/REALISTIC_EXPECTATIONS.md) for
> what success actually looks like.
>
> **Zero accounts needed to start.** The default deploy uses `yfinance` for
> NSE price data and a local paper broker that persists state to a JSON
> file. Once you have 60+ days of paper-trading evidence and you're ready
> for real money, you can wire up Zerodha Kite Connect or Upstox (the two
> popular Indian retail broker APIs) into the same `Broker` interface.

## Guiding principles

1. **No real money until the gate passes.** Paper trading → small-capital live →
   scaled live, in that order, with explicit human sign-off at each step.
2. **Risk before returns.** Pre-trade checks reject orders that breach limits;
   post-trade reconciliation catches divergence.
3. **No future data, no survivorship-clean universes, no random splits.**
   Walk-forward only. See `services/backtest/` and `docs/RISK_POLICY.md`.
4. **Multiple models, multiple data sources.** Ensembles and source redundancy
   are the default. See `services/ml/ensemble.py`.
5. **Auditable.** Every signal, every order, every fill is logged with the
   inputs that produced it. See `services/audit/`.

## High-level architecture

```
                ┌────────────────┐
 market feeds → │   Ingestion    │ → raw store (Parquet/Postgres)
                └────────┬───────┘
                         │
                ┌────────▼───────┐
                │   Features     │ → feature store (Postgres/Redis)
                └────────┬───────┘
                         │
                ┌────────▼───────┐    ┌──────────────┐
                │   ML Engine    │ ←→ │ Model        │
                │  (ensemble)    │    │ Registry     │
                └────────┬───────┘    └──────────────┘
                         │
                ┌────────▼───────┐
                │   Signals      │
                └────────┬───────┘
                         │
                ┌────────▼───────┐    ┌──────────────┐
                │     Risk       │ ←→ │  Portfolio   │
                └────────┬───────┘    └──────────────┘
                         │
                ┌────────▼───────┐
                │   Execution    │ → paper / live broker
                └────────────────┘

  + Audit, Monitoring, Dashboard, API across the stack
```

Full breakdown in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Repository layout

```
libs/                Shared utilities (config, logging, db, types)
services/
  ingestion/         Market data ingestion (yfinance source ships working)
  features/          Technical indicators + feature pipeline
  ml/                Models (LSTM, XGBoost), training (walk-forward), registry
  backtest/          Event-driven backtester with costs/slippage
  risk/              Pre-trade checks, VaR/CVaR, circuit breakers, kill switch
  portfolio/         Position + accounting
  execution/         OMS abstraction, paper broker, live broker stubs
  signals/           Signal aggregation across models
  audit/             Append-only audit log
  api/               FastAPI service (REST + WebSocket)
frontend/            Next.js dashboard
infra/
  k8s/               Kubernetes manifests
  terraform/         Cloud infra (stub)
scripts/             CLI entry points (run_backtest, train_model)
tests/               Pytest suite
docs/                Architecture, roadmap, risk policy, compliance
```

## Quickstart (local, no accounts needed)

Requires Python 3.11+.

```bash
# 1. Python env
python -m venv .venv
. .venv/bin/activate                  # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"

# 2. Smoke test: one daemon cycle on Indian NSE stocks
python scripts/run_daemon.py --run-once --profile conservative

# 3. See what the simulated portfolio looks like
python scripts/show_portfolio.py --currency INR

# 4. Run continuously on the NSE close schedule
python scripts/run_daemon.py        # interactive — pick profile when prompted
```

To trade US markets instead: `python scripts/run_daemon.py --market NYSE` (needs
Alpaca paper keys if you want a real broker, otherwise also uses LocalPaperBroker).

**Read [docs/HOW_TO_RUN.md](docs/HOW_TO_RUN.md) before running** — it's a
short, ordered walkthrough that explains what each piece does and how to
evaluate the results honestly. Also read
[docs/REALISTIC_EXPECTATIONS.md](docs/REALISTIC_EXPECTATIONS.md) to calibrate
what success looks like.

## Deploy (run it 24/7 without your laptop on)

Two options. Pick one based on whether you have a credit card.

### Option A — GitHub Actions cron (free, no credit card)

For daily-at-close trading, GitHub's built-in scheduler is sufficient. Add
your Alpaca paper keys as repo secrets and the daemon fires one cycle every
US trading day at 21:30 UTC. Zero servers to manage.

Full walkthrough: [docs/DEPLOY_GITHUB_ACTIONS.md](docs/DEPLOY_GITHUB_ACTIONS.md)

### Option B — Fly.io (~$0/mo with included credit, requires card)

A real always-on server. ~$3/mo of compute, covered by Fly's $5/mo included
credit. Requires a card for signup verification (not charged unless usage
exceeds the credit, which this won't).

```bash
fly launch --no-deploy --copy-config
fly secrets set ALPACA_API_KEY=... ALPACA_API_SECRET=...
fly volumes create data --size 1 --region iad
fly deploy
fly logs
```

Full walkthrough: [docs/DEPLOY.md](docs/DEPLOY.md)

## Build roadmap

See [docs/ROADMAP.md](docs/ROADMAP.md). Phase 1 (foundations + paper trading)
is what's scaffolded here. Phases 2–5 are the path to live capital.

## Real-money safety gates

Before any live deployment you must pass, in order:

- [ ] 90+ days of green paper trading on the deployed strategy
- [ ] Walk-forward backtest covering 2 distinct market regimes
- [ ] Stress test against 2008, 2020-03, 2022 drawdowns
- [ ] Pre-trade risk checks unit-tested and integration-tested
- [ ] Kill switch verified end-to-end (CLI + API)
- [ ] Reconciliation job catches a deliberately broken fill
- [ ] Compliance review of audit trail
- [ ] Capital deployment plan with staged sizing approved in writing

See [docs/RISK_POLICY.md](docs/RISK_POLICY.md).

## License

Not licensed for redistribution. Internal use only until cleared by counsel.
