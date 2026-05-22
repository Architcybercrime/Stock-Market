# Architecture

This document describes the system as designed, the tradeoffs taken, and where
each subsystem lives.

## Design tenets

1. **Modular services with sharp boundaries.** Each service exposes a small,
   typed interface. Internals can be rewritten without touching callers.
2. **Stateless services, stateful stores.** All state lives in Postgres, Redis,
   or object storage. Services can be restarted or scaled horizontally.
3. **Idempotency everywhere.** Order submission, ingestion, and feature
   computation are idempotent so retries are safe.
4. **No magic.** No global state, no hidden retries, no auto-retraining without
   an explicit trigger and audit entry.
5. **Synchronous in research, asynchronous in production.** Research code is
   straightforward pandas/loops for inspectability. Production paths use async
   IO and queues.

## Subsystems

### Ingestion (`services/ingestion`)

Pulls market data from sources, normalizes it, and writes Parquet to the data
lake and metadata to Postgres.

- **Source abstraction** (`sources/base.py`) — every source implements
  `fetch_bars(symbol, start, end, interval) -> DataFrame`.
- **Working source**: `YFinanceSource` (no API key, daily/hourly).
- **Extension points**: Polygon, Alpaca, IEX, IBKR — sketched, not shipped.
- **Normalizer** adjusts for splits and dividends (yfinance returns adjusted
  series; we keep both raw and adjusted columns).
- **Validation** rejects bars with non-finite OHLC, zero/negative price, or
  out-of-order timestamps.

### Features (`services/features`)

Pure pandas. Every indicator is a function `(DataFrame) -> Series` or
`(DataFrame) -> DataFrame`. No state, no globals. All rolling windows use only
data available **at or before** the current bar — never `.shift(-1)` or
`.rolling(...).mean().shift(0)` with future bars.

Shipped indicators: returns (simple, log), realized volatility, SMA, EMA, RSI,
MACD, Bollinger Bands, ATR, Z-score, momentum, drawdown.

Pipeline composes indicators into a feature matrix with explicit `as_of`
timestamps. Output is cached as Parquet keyed by `(symbol, feature_set, hash)`.

### ML (`services/ml`)

- `models/base.py` — `Model` protocol with `fit`, `predict`, `predict_proba`,
  `save`, `load`.
- `models/lstm.py` — PyTorch Lightning sequence model. Default: 2-layer LSTM,
  hidden=64, dropout=0.2. Predicts next-period log return + uncertainty (via
  MC dropout at inference).
- `models/xgboost_model.py` — XGBoost regressor on engineered features.
- `models/ensemble.py` — Weighted average with per-model confidence scaling.
- `training/walk_forward.py` — Rolling-window walk-forward CV. Default: 5-year
  train, 1-year validate, 1-year step.
- `registry.py` — MLflow-backed model registry. Every model has a version, the
  training data snapshot (hash + range), and the validation metrics frozen at
  registration time.

### Backtest (`services/backtest`)

Event-driven. The engine iterates through time, emitting `BarEvent` /
`SignalEvent` / `OrderEvent` / `FillEvent`. A strategy receives bars and emits
orders. The execution simulator applies cost, slippage, and partial-fill rules
to produce fills. The portfolio updates positions and P&L from fills.

Defaults:
- Commission: 0.5 bps (configurable)
- Slippage: half-spread + impact = `0.5 * spread + 0.1 * (qty / adv) * price`
- Latency: 1 bar (orders submitted on bar `t` fill at bar `t+1` open)

Metrics: total return, CAGR, vol, Sharpe (rf=0), Sortino, max DD, Calmar, win
rate, profit factor, turnover, hit rate. All computed from the fill log, not
from the strategy's claimed P&L.

### Risk (`services/risk`)

- `checks.py` — pre-trade gate. Each order goes through every check; if any
  rejects, the order is logged and dropped. Checks are pure functions of
  `(order, portfolio_state, limits)`.
- `limits.py` — `RiskLimits` dataclass loaded from env or DB.
- `var.py` — historical and parametric VaR + CVaR.
- `circuit_breaker.py` — peak-to-trough drawdown trigger; once tripped, all
  trading is halted until manually cleared. Also a daily-loss trigger.
- `kill_switch.py` — file-based + API-based emergency stop. Checked on every
  order submission.

### Portfolio (`services/portfolio`)

Double-entry-style accounting. Positions tracked at the lot level (FIFO).
Realized vs unrealized P&L separated. Cash balance, margin, leverage tracked.

### Execution (`services/execution`)

- `oms.py` — order state machine: `PENDING -> SUBMITTED -> PARTIALLY_FILLED -> FILLED | CANCELLED | REJECTED`.
- `brokers/base.py` — `Broker` protocol.
- `brokers/paper.py` — paper broker using live or replayed market data.
- `brokers/alpaca.py` — stub for Alpaca live; gated behind
  `LIVE_TRADING_ENABLED`.
- `reconciliation.py` — periodic job comparing expected vs actual fills.

### Signals (`services/signals`)

Takes per-model predictions plus market state, produces unified `Signal` objects
with `(symbol, direction, target_weight, confidence, horizon, rationale)`.
Confidence is calibrated (isotonic regression against historical hit rate).

### Audit (`services/audit`)

Append-only log of every decision and action: signal generated, order
submitted, fill received, limit tripped, kill switch pressed. Writes to Postgres
with hash-chain integrity (each row references the SHA-256 of the previous
row's payload).

### API (`services/api`)

FastAPI app. Routes:
- `GET /healthz`, `GET /readyz`
- `GET /signals` — current signals
- `GET /portfolio` — positions, P&L, risk metrics
- `GET /risk/status` — limit utilization, circuit breaker state
- `POST /risk/kill` — engage kill switch (requires elevated role)
- `WS /ws/ticks` — streamed market ticks for the dashboard
- `GET /metrics` — Prometheus exposition

Auth: OAuth2 password flow → JWT. Two roles: `viewer` and `operator`. Live
trading actions additionally require an `MFA`-claim JWT (out of scope here but
the role check is wired).

## Data flow at runtime

```
1. Ingestion writes new bar (Parquet + Postgres metadata).
2. Feature service reads bar, computes incremental features, writes to feature
   store (Redis hot / Postgres cold).
3. ML service consumes features, runs ensemble inference, emits PredictionEvent.
4. Signal service reconciles predictions across models, emits Signal.
5. Strategy turns Signal into target weights, generates Orders.
6. Risk service approves or rejects each Order.
7. OMS submits approved Orders to broker.
8. Broker callbacks update Fills.
9. Portfolio updates positions and P&L from Fills.
10. Audit logs every step. API surfaces state. Dashboard reads API.
```

## What is intentionally not yet built

- Tick-level order book ingestion (the design supports it; no source ships).
- RL agents (training environment exists conceptually but is not implemented).
- GNN inter-stock model (research code, not productionized).
- Federated learning, synthetic data, NAS — flagged in roadmap as Phase 5+.
- Mobile UI.

## Scaling notes

- **Vertical first**: a single Postgres + Redis + 4-CPU API handles 100s of
  symbols at minute bars. Profile before sharding.
- **Kafka comes in** when (a) multiple downstream consumers need the same tick
  stream or (b) you exceed ~5k msgs/sec.
- **GPU only for training and Transformer inference.** LSTM inference on
  100 symbols every minute fits comfortably on CPU.
- **Model registry sharded by symbol** if model count exceeds ~10k.
