# How to run the autonomous trading daemon

This guide walks you from zero to a daemon that paper-trades for you on a
schedule. **Do not skip steps.** Each one is there for a reason.

## 0. Read this first

The daemon makes its own buy/sell decisions every market close. You will NOT
be telling it what to trade. You ARE telling it:

- How aggressive to be (risk profile)
- Which stocks it can pick from (universe)
- What broker to use (Alpaca paper by default)

It is **not** a money-printing machine. It is a disciplined, transparent way
to test whether a systematic strategy works in real time on real data —
without risking real money until you trust it.

If you cannot afford to lose the eventual real-money capital you'd point at
this, **stop reading and put your money in an index fund**. This is the
honest answer.

## 1. Set up Alpaca (free, ~5 minutes)

1. Go to <https://alpaca.markets> and sign up.
2. In the dashboard, switch to "Paper Trading" (top of the page).
3. Click "Generate Keys" — you get an `API Key` and `Secret`.
4. Copy them.

## 2. Configure local environment

```bash
cp .env.example .env
```

Edit `.env`:

```
ALPACA_API_KEY=PKxxxxxxxxxxxxxxxxxx
ALPACA_API_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
ALPACA_BASE_URL=https://paper-api.alpaca.markets   # paper, do not change yet

TRADING_MODE=paper
LIVE_TRADING_ENABLED=false
```

Leave the live flags off. Even if you try to flip them now, the broker
refuses without the kill switch file being gone and the URL being switched.
That's deliberate.

## 3. Install dependencies

```bash
python -m venv .venv
. .venv/bin/activate                  # mac/linux
.\.venv\Scripts\activate              # windows
pip install -e ".[dev]"
```

## 4. (Optional) Train models for the ML signal

The ML signal generator can run *without* trained models — it'll just
contribute zero with low confidence, which is the honest fallback. If you
want it to participate, train one model per symbol:

```bash
# Pull a few years of history for the ML training set
python scripts/ingest_history.py --symbols AAPL MSFT SPY --start 2018-01-01

# Train an ensemble for one symbol (repeat per symbol)
python scripts/train_model.py --symbol AAPL --model ensemble
```

Each training run produces walk-forward validation metrics. Look at
`mean_r2` — if it's negative or near zero, the model has no edge and the
daemon's MLSignal will correctly down-weight it.

## 5. Smoke test the daemon (one cycle, no scheduler)

```bash
python scripts/run_daemon.py --run-once --profile conservative
```

What you'll see:
- A banner confirming paper mode.
- A summary of the chosen profile.
- Per-strategy per-symbol signal logs.
- A final block: which symbols got selected, what target weight each one
  got, and which orders got submitted vs rejected.

If anything looks wrong — for example, every signal has zero confidence —
stop and investigate. Don't move on.

## 6. Let it run on a schedule

```bash
python scripts/run_daemon.py
```

Pick a profile when prompted. The scheduler computes the next US market
close, sleeps until ~5 minutes after the bell, runs one decision cycle,
then sleeps until the next close. Ctrl-C stops it cleanly.

For 24/7 operation, run it inside a `screen`/`tmux` session, or as a
systemd unit / Windows scheduled task / Kubernetes Deployment.

## 7. Watch what it does

- **Logs**: every signal, every decision, every order shows up in stdout.
  Pipe to a file for review:
  `python scripts/run_daemon.py > daemon.log 2>&1`
- **Dashboard**: `make api` in one terminal, `make frontend` in another,
  visit <http://localhost:3000>. Login with `viewer/viewer`. The dashboard
  pulls positions and risk state from the same broker the daemon uses.
- **Alpaca's web UI**: <https://app.alpaca.markets> shows your paper
  account, all orders, all fills.

## 8. Evaluation discipline

After running the daemon, hold yourself to these rules:

| Time elapsed | Evaluate by |
|---|---|
| < 14 days | **Do not evaluate.** Sample size too small. |
| 14–60 days | Look at process: are orders being submitted? Are rejections sensible? Any errors? |
| 60+ days | Compare net return to a benchmark (SPY buy-and-hold over the same period). Look at Sharpe, max drawdown, hit rate. |
| 90+ days | If results are reasonable, this is the gate to consider Phase 3 (small live capital). See [ROADMAP.md](ROADMAP.md). |

**Reasonable** does not mean "beat the market." For a paper run of a
conservative profile, reasonable means:

- Net return roughly tracks the market (within ±5%).
- Max drawdown < the market's max drawdown over the same window.
- No risk-limit breaches.
- No data-feed gaps that went undetected.

If the system is dramatically *outperforming* the market in paper mode, be
suspicious — it usually means a data lookahead bug or a fluky window. Real
edges are small.

## 9. If you want to go live

Read [docs/ROADMAP.md](ROADMAP.md) and [docs/RISK_POLICY.md](RISK_POLICY.md).
Then read them again. Then talk to your accountant about tax implications.
Then run paper for 90+ more days at the larger size you intend to deploy.
Then maybe — at 1% of your intended real-money size — flip the switch.

The exact sequence is in [docs/REALISTIC_EXPECTATIONS.md](REALISTIC_EXPECTATIONS.md).
