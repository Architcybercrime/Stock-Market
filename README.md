# Stock_Market — Institutional AI Trading Platform

A production-oriented, modular AI trading and decision-support platform. Built with
capital preservation first, risk-adjusted returns second, automation third.

> **Status: scaffold.** This repository is the initial architecture and working
> foundation. Several subsystems contain real, runnable implementations
> (ingestion, indicators, backtester, risk checks, FastAPI service); others are
> extension points with clearly marked TODOs. No component is "magic." Read the
> code before trusting it with capital.

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

## Quickstart (local)

Requires Python 3.11+, Node 20+. Alpaca paper account (free, 5 min signup).

```bash
# 1. Python env
python -m venv .venv
. .venv/bin/activate                  # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"

# 2. Configure Alpaca paper credentials in .env (see docs/HOW_TO_RUN.md)
cp .env.example .env

# 3. Smoke test: one cycle of the autonomous daemon
python scripts/run_daemon.py --run-once --profile conservative

# 4. Run forever on the market-close schedule
python scripts/run_daemon.py     # interactive — pick profile when prompted

# 5. Watch via dashboard (in two more terminals)
make api                          # FastAPI on :8000
make frontend                     # Next.js dashboard on :3000
```

**Read [docs/HOW_TO_RUN.md](docs/HOW_TO_RUN.md) before running** — it's a
short, ordered walkthrough that explains what each piece does and how to
evaluate the results honestly. Also read
[docs/REALISTIC_EXPECTATIONS.md](docs/REALISTIC_EXPECTATIONS.md) to calibrate
what success looks like.

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
