# Build Roadmap

Phased path from scaffold to live capital. Each phase has an explicit exit gate.
Do **not** advance a phase until its gate is signed off.

## Phase 0 — Scaffold (this commit)

What's in: repo structure, working ingestion (yfinance), indicators,
walk-forward training (LSTM + XGBoost), event-driven backtester, pre-trade
risk checks, paper broker, FastAPI service, Next.js dashboard skeleton, CI.

**Gate to Phase 1**: `make test` passes, `make backtest` runs end-to-end with
sample symbols, and the API serves `/healthz`.

## Phase 1 — Research foundation (weeks 1–6)

- Add Polygon or Alpaca data source for minute bars.
- Expand indicator library, add cross-asset features (sector/index relative
  strength, term-structure features).
- Build feature store (Redis hot tier + Postgres cold tier) with versioning.
- Walk-forward backtest 3 baseline strategies (momentum, mean-reversion,
  long-short factor) on S&P 500 universe with delisted stocks.
- Set up MLflow tracking; every backtest produces a tracked run.

**Gate to Phase 2**: At least one strategy has positive net-of-costs Sharpe
> 0.5 over walk-forward periods covering 2018–2024 including 2020 and 2022
drawdowns. Survivorship bias eliminated.

## Phase 2 — Paper trading (weeks 7–14)

- Wire paper broker to live data feed (delayed is fine).
- Run shadow trading: signals generated, orders simulated, no real fills.
- Build dashboard widgets: live P&L, risk gauge, model health, data freshness.
- Implement reconciliation between intended vs simulated fills.
- Drift detection on features and model predictions.
- Kill switch tested with chaos drills (kill API, kill data feed, watch behavior).

**Gate to Phase 3**: 90 consecutive days of paper trading where:
- Daily P&L stays within ±2σ of backtested distribution.
- No risk limit breach.
- No data outage that wasn't detected and alerted within 60s.
- Reconciliation discrepancies resolved within 1 trading day.

## Phase 3 — Small live capital (weeks 15–24)

- Move to broker with real fills (Alpaca / IBKR). Start at 1% of paper size.
- Add execution-quality monitoring (slippage vs model, fill rate, queue
  position estimates).
- Compliance review of audit trail with counsel.
- Add daily P&L attribution: how much from each strategy, factor, symbol.
- Cap at predetermined notional. Hard-code the cap in `risk/limits.py` and
  require code change + review to lift.

**Gate to Phase 4**: 60 trading days at small size with:
- Net-of-costs return within 30% of backtested expectation.
- All execution-quality metrics within tolerance.
- Zero compliance issues.
- Documented incident response for at least one drill.

## Phase 4 — Scaled live (months 6–12)

- Expand notional in increments of 2× with a 30-day observation between steps.
- Add more strategies and models. Ensemble across them.
- Build regime detection and adaptive weighting.
- Add stress testing pipeline (2008, 2020-03, 2022 replays nightly).
- Disaster recovery drill (loss of primary region).

## Phase 5 — Research-edge features (month 12+)

- RL agent for execution (child order placement).
- GNN for cross-asset relationships.
- Alternative data integration (sentiment, satellite).
- Federated learning across business units if applicable.
- Continuous retraining pipeline with concept-drift triggers.

## Hard rules across all phases

- No live trading without LIVE_TRADING_ENABLED=true and explicit operator MFA.
- No model deployed to live without a signed validation report.
- No strategy without a clearly stated edge hypothesis.
- No backtest result quoted without walk-forward and cost assumptions.
- All changes to risk/limits.py require two-person review.
