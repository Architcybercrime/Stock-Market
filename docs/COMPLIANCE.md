# Compliance & Legal Checklist

This is an engineering checklist, not legal advice. Engage counsel before
operating with real capital, especially across jurisdictions.

## Regulatory regimes touched

| Activity | US | EU/UK |
|---|---|---|
| Algorithmic trading on regulated exchanges | SEC Rule 15c3-5 (Market Access Rule), Reg SCI | MiFID II Art. 17 |
| Market data redistribution | Exchange-specific licenses | Exchange-specific |
| Investment advice (if offered to clients) | RIA registration (state or SEC) | MiFID II investment-firm authorization |
| Customer funds custody | Broker-dealer registration | MiFID II custody rules |

For internal proprietary trading from your own capital, the bar is lower
(no advisor registration, no custody rules). For client-facing services it is
substantially higher.

## Audit trail requirements

The audit log in `services/audit/` must capture, with sequenced timestamps,
**every** event from signal generation to fill:

- Signal: model id + version, input feature hash, output, confidence.
- Pre-trade decision: which checks passed/failed and why.
- Order: full order spec + parent strategy + signal id.
- Submission: broker request payload, response, latency.
- Fills: every partial fill with exchange + venue + price + quantity.
- Cancellations / rejections: reason from broker.
- Limit changes: who changed what, when, with prior values.
- Kill switch events: who engaged, when, what was in flight.

The audit log uses a **hash chain**: row N contains SHA-256 of row N-1's
canonical JSON payload. Tampering is detectable.

Retention: 7 years minimum (US broker-dealer requirement; even for
proprietary trading this is a sensible default).

## Market data licensing

- **Free sources** (yfinance, Yahoo): no commercial license. Use for research
  and personal use only. Do not use for client-facing advice or redistribute.
- **Paid sources** (Polygon, IEX Cloud, Bloomberg, Refinitiv): subject to
  per-license redistribution and display rules. Most paid feeds prohibit
  displaying their data to third parties without separate license.
- **Exchange direct feeds** (CME, NYSE, NASDAQ): heaviest licensing; require
  separate Pro/Non-Pro user classifications and reporting.

The data layer tags each bar with its source so we can enforce "do not
redisplay" rules in the dashboard.

## Pre-trade risk controls (Market Access Rule)

SEC 15c3-5 requires brokers to enforce pre-trade controls; if we route through
a broker, they enforce. We additionally enforce our own (in
`services/risk/checks.py`) so we never depend solely on the broker.

ESMA / MiFID II Art. 17 requires algorithmic trading firms to:

- Maintain effective systems and risk controls.
- Test algorithms before deployment.
- Document and review trading systems.
- Have business continuity arrangements.
- Maintain records sufficient to reconstruct trading activity.

All five are addressed in the architecture and roadmap.

## Best execution

For client-facing operation, document the venue selection logic in
`services/execution/`. For now (paper trading + proprietary) we keep a fill
quality log but no formal best-ex policy.

## Anti-manipulation

The system must not produce orders that constitute:

- **Spoofing**: orders not intended to be filled.
- **Layering**: stacked non-bona-fide orders.
- **Marking the close / open**: timed orders to influence print prices.
- **Wash trading**: self-crossing.

Enforcement:

- Pre-trade checks reject orders the strategy itself flags as
  non-bona-fide (no such strategies are shipped).
- Surveillance job runs nightly to detect patterns above
  (`scripts/surveillance.py`, future work).
- No strategy may submit and cancel within < 100ms on the same level (default
  in `risk/limits.py`).

## Disclosures (if client-facing)

- "Past performance is not indicative of future results."
- Methodology disclosure: model approach, data sources, key assumptions.
- Material risk factors disclosure.
- Conflicts of interest disclosure if any.

## Model risk

Per SR 11-7 (US Fed model risk guidance) and analogous EU guidance:

- Every production model has a validation report (independent reviewer).
- Models are inventoried in the registry with owner, validator, last review.
- Backtest vs live divergence triggers re-validation.

## Personal data

No personal data is processed by the current scaffold. If onboarding clients,
GDPR / CCPA obligations apply; do not start until a DPIA is complete.

## Checklist before live trading

- [ ] Broker-dealer / RIA status confirmed appropriate to activity
- [ ] Data licenses cover intended use
- [ ] Audit retention configured to ≥ 7 years
- [ ] Pre-trade controls tested and signed off
- [ ] Best-ex policy documented (if client-facing)
- [ ] Disaster recovery procedure tested
- [ ] Counsel reviewed strategy descriptions and disclosures
- [ ] Insurance reviewed (E&O if advisory)
- [ ] Incident response plan documented
