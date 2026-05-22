# Realistic expectations

> Every quant operation that lasts has internalized this document. Every one
> that blows up did not.

## The accuracy myth

A model that achieves 80% directional accuracy on real markets does not
exist outside of overfit backtests, lookahead bugs, or marketing decks.

Numbers from the actual literature:

| System | Directional accuracy | Annual return |
|---|---|---|
| Random guess | 50% | 0% |
| "Tomorrow = today" baseline | ~50–55% | benchmark drift |
| Most published academic strategies | 51–53% | 1–4% above benchmark, net of costs |
| Renaissance Medallion (best ever) | ~52% (estimated) | 39% net of fees over 30 years |
| Top retail systematic operators | 52–55% | 5–15% above benchmark in good years |
| Most retail "AI trading systems" sold online | 50% (random) | Negative once costs included |

The system you're running is most likely in the bottom two rows. That is
not a failure — it's the honest expectation. The reason it can still be
worthwhile:

1. **Discipline**: it never panics, never revenge-trades, never holds a
   loser hoping it comes back.
2. **Diversification**: 5–12 positions reduces idiosyncratic risk.
3. **Cost control**: you trade weekly, not daily, on commission-free Alpaca.
4. **Audit trail**: every decision is logged. You can actually learn from
   what worked and what didn't.

## Why "accuracy" is the wrong metric

Two strategies, both real:

**Strategy A**: 80% accuracy. Wins are 1% each. Losses are 5% each.
Expectancy = 0.8 × 1% − 0.2 × 5% = **−0.2% per trade**. You lose money.

**Strategy B**: 45% accuracy. Wins are 3% each. Losses are 1% each.
Expectancy = 0.45 × 3% − 0.55 × 1% = **+0.8% per trade**. You make money.

The system optimizes for **expectancy × Sharpe ratio × drawdown survival**,
not accuracy. If you ask "what's the win rate" first, you're asking the
wrong question.

## Realistic outcomes by profile

These are **paper-trading** ranges. Live trading will be 10–30% worse than
paper due to real fills + slippage + emotional override.

| Profile | Annual return (median) | Worst drawdown | Win rate | Trades/year |
|---|---|---|---|---|
| Conservative | 4–10% | 8–15% | 50–55% | 30–60 |
| Balanced | 6–14% | 12–22% | 48–53% | 80–150 |
| Aggressive | 8–20% (or losses) | 18–35% | 46–52% | 200–400 |

The "or losses" in Aggressive is honest. Concentrated, higher-turnover
strategies have wider outcome distributions. Some years they beat the
market by 15%; some years they lose 25%. The conservative profile has a
much tighter distribution — usually boring, occasionally good.

## What you should *not* expect

- **Beating the S&P 500 every year.** Even Buffett doesn't.
- **Predicting crashes.** No model in this codebase has any chance of
  consistently calling the timing of a 2008-style event.
- **Linear equity curve.** Drawdowns are guaranteed. They're not bugs.
- **The same backtest result going forward.** Backtests are a *floor* on
  what could happen, not a ceiling.

## What you should expect

- **Mostly boring days.** A handful of orders per week. Long stretches
  where the system does nothing because nothing meets its thresholds.
- **Trailing the market for months at a time.** Especially if the market
  is in a single-direction trend, a multi-strategy system will look slow.
- **Confusing-looking trades.** The system will sometimes buy a stock that
  looks "obviously" bad to you, or pass on one that's "obviously" good.
  That's the point of automating it — you don't get to override.

## The deployment ladder

```
Phase 1: Scaffolded (done) ────────────────────────────────────┐
                                                                 │
                                                                 ▼
Phase 2: Paper trading, conservative profile ─────► 90 days, no errors,
                                                    process works
                                                                 │
                                                                 ▼
Phase 3: Paper trading, profile of choice ─────► 90 more days, paper
                                                    P&L behaves
                                                                 │
                                                                 ▼
Phase 4: Live, $100 cap ─────► 30 trading days, real fills match paper
        (hardcoded in risk/limits.py)                            │
                                                                 ▼
Phase 5: Live, $1,000 cap ─────► 60 trading days                 │
                                                                 ▼
Phase 6: Live, $10,000 cap ─────► 60 trading days                │
                                                                 ▼
                  (and so on, doubling every 60 days only if metrics hold)
```

Each phase's gate is **paper-vs-live divergence**: if the live result
diverges from what paper said by more than 1.5×, you go back a step. No
exceptions, no "this time is different."

## Why this matters more than the code

The code I shipped is an honest scaffold. The math, the indicators, the
backtest engine, the risk checks — they are reasonable. They are not
magic.

The thing that actually decides whether you end up with more money or less
money is **discipline**:

1. Following the deployment ladder above without skipping rungs.
2. Not jacking up position sizes after a winning streak.
3. Not reducing position sizes after a losing streak.
4. Reading the audit log every week and asking "is the system doing what
   I expected?"
5. Calling it off if the answer is "no" — not "tweaking" the parameters
   until it looks fine again. Tweaking is overfitting in slow motion.

If you can do those five things, this system has a real chance of making
you a small positive return over multiple years. If you can't, no system
will save you. Buy index funds.
