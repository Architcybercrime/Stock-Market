# Deploy via GitHub Actions (free, no credit card)

This is the lowest-friction way to run the daemon. No cloud signup, no card.
Everything happens inside GitHub.

## How it works

- A scheduled GitHub Actions workflow fires once per US trading day, 30 min
  after market close (21:30 UTC year-round).
- The workflow spins up a temporary Ubuntu runner, installs the project,
  reads your Alpaca paper API keys from GitHub repo secrets, runs **one
  cycle** of the daemon (`python scripts/run_daemon.py --run-once --profile conservative`),
  then shuts down.
- All persistent state (positions, orders, fills) lives at Alpaca. There is
  no server to maintain.
- You watch via Alpaca's web UI + the Actions tab in GitHub.

**Cost:** $0. Public repos get unlimited free Actions minutes.

**Tradeoffs vs a real always-on daemon:**

- Single cycle per day, not continuous — but that's all daily-close trading
  needs.
- No persistent kill-switch file. Instead, you get a one-click manual
  workflow that flattens all positions in an emergency (see below).
- Trained ML models would need to be committed to the repo or rebuilt in CI
  each run. Momentum + mean reversion work without any trained model.

---

## 1. Get your Alpaca paper API keys

Already covered in [docs/HOW_TO_RUN.md](HOW_TO_RUN.md). You need:

- `ALPACA_API_KEY` — starts with `PK...`
- `ALPACA_API_SECRET` — 40-char random string

Make sure your account toggle is on **Paper** before generating the keys.

---

## 2. Add the keys to your GitHub repo as secrets

1. Go to your repo on GitHub: <https://github.com/Architcybercrime/Stock-Market>
2. **Settings** (top tab) → **Secrets and variables** (left sidebar) → **Actions**
3. Click **New repository secret**
4. Add two secrets one at a time:

   | Name | Value |
   |---|---|
   | `ALPACA_API_KEY` | your PK... key |
   | `ALPACA_API_SECRET` | your 40-char secret |

5. (Optional) add `JWT_SECRET` with any random string. Not used by the
   daemon but required by pydantic settings parsing.

Once saved, you cannot view a secret's value again — only update it. That's
expected.

---

## 3. Enable Actions on the repo (if not already)

If you've never run an action on this repo, GitHub may show a banner asking
you to enable workflows. Click **I understand my workflows, enable them**.

Otherwise: go to the **Actions** tab — if you see the workflows listed,
they're enabled.

---

## 4. Test with a manual run

Don't wait until tomorrow's 21:30 UTC — test it now:

1. Go to **Actions** tab
2. In the left sidebar, click **Daily paper-trade cycle**
3. Click the **Run workflow** dropdown (top right)
4. Choose a profile (`conservative` by default)
5. Click the green **Run workflow** button

Wait ~30 seconds, then refresh. You should see a new run appearing. Click it
to watch the logs in real time.

Expected output in the logs:

```
[mode] paper trading — no real money will be moved.
[profile] conservative: Long-only, mostly cash...
[broker] alpaca (paper=True)
[universe] 16 symbols: AAPL MSFT GOOGL AMZN NVDA META TSLA JPM...
[result] nav=$100000.00 selected=N attempted=N accepted=N rejected=N
[selected positions]
  AAPL  target_weight=4.2%  conf=0.71  12-1 ret=+5.4% ...
  ...
```

If it errors out:
- `AlpacaBroker requires ALPACA_API_KEY...` → secrets not set or typo'd.
  Recheck step 2.
- Other Python errors → copy the traceback and share, I'll help debug.

---

## 5. Verify orders landed at Alpaca

1. Go to <https://app.alpaca.markets/paper/dashboard/overview>
2. Look at **Orders** tab → you should see any orders the workflow submitted
3. **Positions** tab → if it was a fresh account, you'll see new positions
4. Each order's status field tells you if it filled, is pending, or was
   rejected (e.g. "wash trade" rejections are normal during testing)

---

## 6. Day-to-day rhythm

- The cron fires **every weekday at 21:30 UTC** automatically. You don't do
  anything.
- Each run shows up in the Actions tab with a green check or red X.
- A red X = the workflow errored. Click the run, read the failed step.
- Weekly habit: open the Actions tab, scan the last 5 runs, make sure they
  all ended with a sensible `[result] nav=$... selected=N` line.

---

## 7. Changing the risk profile

Two options:

**For one specific run** — go to Actions → Daily paper-trade cycle → Run
workflow → pick `balanced` or `aggressive` from the dropdown. The next
scheduled run goes back to `conservative` unless you edit the workflow.

**Permanently** — edit `.github/workflows/daily_trade.yml`, change
`default: "conservative"` to the profile you want, commit, push. From
that commit on, every scheduled run uses the new default.

---

## 8. Emergency stop — flatten all positions

The "kill switch" in this deploy is a second workflow:

1. Actions tab → **Emergency flatten (sell all positions)** in the left sidebar
2. **Run workflow** → in the confirmation box, type exactly: **`FLATTEN ALL`**
3. Click the green button

The workflow cancels every open order and submits market sells for every
position. Done in seconds. Use this if:

- You see the system doing something you don't understand
- Alpaca shows unexpected activity
- You want to take a break and come back later

The scheduled workflow will still run tomorrow. If you want to pause it
entirely, see Section 10.

---

## 9. Changing the symbol universe

The default universe is in `scripts/run_daemon.py` at the top:

```python
DEFAULT_UNIVERSE = [
    "AAPL", "MSFT", "GOOGL", ...
]
```

To change it, edit that list, commit, push. The next scheduled run picks it
up. Keep the list to liquid US stocks/ETFs (>$1B market cap, >$10M daily
volume) — illiquid names will have huge slippage even on paper.

---

## 10. Pausing or stopping

**Pause for a while (e.g. you're traveling):**

- Actions tab → **Daily paper-trade cycle** → **... (top right)** → **Disable workflow**

The cron stops firing. Re-enable the same way.

**Tear down entirely:**

- Disable both workflows
- Remove the secrets from Settings → Secrets and variables → Actions
- Optionally delete the workflow files

Your Alpaca paper account stays open with whatever positions are sitting in
it. You can flatten them manually at Alpaca's web UI or with one more run
of the **Emergency flatten** workflow.

---

## 11. The "I want a real always-on daemon eventually" path

GitHub Actions cron is fine for daily-close trading and 90+ days of paper
evaluation. If, after that, you want intra-day or real-time trading, you'll
need a real server. Options at that point:

- **Fly.io** — needs a credit card; ~$3/mo covered by free credit. See [DEPLOY.md](DEPLOY.md).
- **DigitalOcean / Linode / Hetzner droplet** — $4-6/mo, need card or
  PayPal. Self-managed VM.
- **Oracle Cloud Free Tier** — always-free ARM VMs, but signup also needs a card.
- **Home server / Raspberry Pi** — truly $0 if you have the hardware. Plug
  it in, install Docker, run the daemon container.

None of these are urgent. Daily cron is plenty until you have months of
evidence that the system behaves and you want more.

---

## Troubleshooting

**"Workflow not running on schedule"**
- GitHub disables scheduled workflows on inactive repos (no commits for 60
  days). If yours has been idle, push any commit (even a README typo) to
  re-activate.

**"Permission denied" or "API token expired"**
- Regenerate Alpaca keys in the Alpaca UI, update the GitHub secret. Run
  the workflow manually to verify.

**"Pattern day trading" or "buying power" errors in logs**
- Alpaca's paper accounts default to $100,000 simulated equity. If you
  somehow blew through it or the system tries to leverage past your cash,
  these warnings appear. The pre-trade risk checks in our code should
  prevent this, but Alpaca will also block from their side.

**"No new orders even though signals look good"**
- The daemon's rebalance threshold means small drifts don't trigger trades.
  This is intentional — it keeps cost drag down. Check the logs for lines
  starting with `daemon.intended_order` vs `daemon.signal`. If signals are
  generating but no orders, your current positions are already close to target.

**"Holiday and the workflow still ran"**
- That's expected. The cron is "weekdays" only; US trading holidays are not
  filtered. The daemon usually just doesn't trade (signals haven't changed
  from yesterday) or Alpaca queues orders for the next open. Harmless.
