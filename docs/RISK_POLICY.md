# Risk Policy

Risk management is a **first-class subsystem**, not a layer applied at the end.
Every order passes through `services/risk/checks.py` before reaching a broker.

## Hard limits (default, configurable via env)

| Limit | Default | Enforced where |
|---|---|---|
| Max daily loss (% NAV) | 2% | `circuit_breaker.py` |
| Max drawdown peak-to-trough | 10% | `circuit_breaker.py` |
| Max single position (% NAV) | 5% | `checks.position_size_check` |
| Max sector exposure (% NAV) | 25% | `checks.sector_exposure_check` |
| Max gross leverage | 1.0× | `checks.leverage_check` |
| Min cash buffer (% NAV) | 5% | `checks.cash_buffer_check` |
| Max orders per minute | 60 | `checks.rate_limit_check` |
| Max notional per order (% NAV) | 2% | `checks.order_size_check` |

Triggering any **circuit breaker** halts all new trading and notifies operators.
Clearing requires an authenticated operator action via API.

## Pre-trade checks

Every order must pass, in order:

1. Kill switch is not engaged.
2. Trading mode matches order intent (paper vs live).
3. Symbol is on the approved list.
4. Order notional within per-order limit.
5. Resulting position within per-symbol limit.
6. Resulting sector exposure within sector limit.
7. Resulting gross leverage within leverage limit.
8. Cash buffer maintained.
9. Rate limit not exceeded.
10. VaR contribution within budget.

If any check fails, the order is logged to the audit trail with the reason and
dropped. The signal is preserved so attribution remains accurate.

## VaR methodology

- **Historical VaR**: 99% one-day, rolling 252-day window.
- **CVaR (Expected Shortfall)**: average of the worst 1% of historical
  returns over the same window.
- **Parametric VaR** (sanity check): variance-covariance with shrinkage
  estimator (Ledoit-Wolf).

VaR is computed on the portfolio level **and** as the marginal contribution of
each prospective trade. If a new trade would push portfolio VaR above the budget,
the trade is rejected even if it passes per-symbol limits.

## Position sizing

Default: volatility-targeting. Each position is sized so its standalone
volatility contribution equals a target (e.g., 1% of NAV daily vol).

Optional: fractional Kelly (capped at 0.25 Kelly to avoid the "Kelly is a
upper bound, not a target" trap).

## Circuit breakers

Modeled on exchange circuit breakers (Reg NMS 7/13/20%) but tighter:

| Trigger | Action |
|---|---|
| Daily P&L < −2% NAV | Halt new entries; existing positions allowed to exit |
| Drawdown ≥ 10% from peak | Halt all trading; flatten or hedge per playbook |
| 3 consecutive failed risk checks within 60s | Halt new orders, page operator |
| Data feed staleness > 60s on traded symbol | Halt orders on that symbol |
| Model prediction outside historical 99.9% range | Drop signal, log anomaly |

## Kill switch

- **File-based**: presence of `KILL_SWITCH` file in the data root blocks all
  orders. Survives restarts. Operations can disable trading without code access.
- **API-based**: `POST /risk/kill` with operator credentials. Same effect.
- Both modes are checked on every order submission, not cached.

## Stress tests

Before any new strategy goes live, replay through:

- 2008-09 (GFC)
- 2018-02 (vol-mageddon)
- 2020-03 (COVID crash)
- 2022 (rate-driven drawdown)
- 2010-05-06 (flash crash, intraday)

A strategy is rejected if any scenario produces a >25% drawdown, regardless of
backtest Sharpe.

## What this policy does NOT cover

- Counterparty risk (assumed mitigated by using regulated brokers).
- Operational risk (covered in `docs/COMPLIANCE.md` and runbooks).
- Model interpretability for regulators (covered in compliance).

## Changing this policy

The values in `services/risk/limits.py` are the source of truth. Changing them
requires:

1. A pull request explaining the rationale.
2. Two-person review (one from quant, one from risk).
3. A re-run of the relevant stress tests with the new limits.
4. Sign-off recorded in the audit trail.
