# Deploy to Fly.io (paper trading, always on)

This is the cheapest reliable way to run the daemon 24/7. Total cost: ~$2-3/mo,
covered by Fly's included $5/month free credit. So in practice, **$0**.

You will need:

- An Alpaca paper-trading account (free, 5 min)
- A Fly.io account (free signup, **requires a credit card** for verification; not charged unless you exceed the $5 credit)
- The `flyctl` CLI installed on this machine
- About 15 minutes total

The repo is already configured: `fly.toml`, `.dockerignore`, and the worker
Dockerfile are in place. You just need to run a few commands.

---

## 1. Get Alpaca keys (5 min)

1. Sign up at <https://alpaca.markets>.
2. After signup, in the dashboard, ensure you are on **Paper Trading** (toggle
   in the top bar). Real money is on a different tab; we are not touching it.
3. In the left sidebar: **Paper Overview** → **Generate API Keys**.
4. Copy the **API Key ID** and **Secret Key** somewhere safe. You will not see
   the secret again — if you lose it, regenerate.

Do NOT paste these into `.env` and commit. They go into Fly secrets, separately.

---

## 2. Install flyctl (2 min)

**Windows (PowerShell):**

```powershell
iwr https://fly.io/install.ps1 -useb | iex
# Then restart your terminal so PATH picks it up
```

**macOS / Linux:**

```bash
curl -L https://fly.io/install.sh | sh
```

Verify:

```bash
fly version
```

---

## 3. Log into Fly (1 min)

```bash
fly auth signup     # if new
# or
fly auth login      # if existing
```

A browser window opens, you authorize, terminal becomes authenticated.

You will be asked for a credit card. Fly requires it for verification.
You will **not** be charged unless your usage exceeds $5/month, which this
deployment will not.

---

## 4. Pick an app name (1 min)

The default in `fly.toml` is `stock-market-daemon`. Fly app names are global
across all users, so this might be taken. If you want a different name:

```bash
# Pick something unique to you, e.g. your initials
# Edit fly.toml and change the line: app = "stock-market-daemon"
# to:                                 app = "ac-stock-daemon"
```

Save the file before continuing.

---

## 5. Initialize the Fly app (1 min)

From the repo root (`D:/Stock_Market`):

```bash
fly launch --no-deploy --copy-config --name stock-market-daemon
```

> Replace `stock-market-daemon` with whatever you put in `fly.toml`.

`--no-deploy` is important: it creates the app on Fly but does NOT push the
container yet, because we still need to set secrets and create the volume.

`--copy-config` tells fly to use the `fly.toml` already in the repo rather
than asking interactive questions.

If it asks "Would you like to set up Postgres?" — say **No**. We don't need it.
Same for Redis or Sentry.

---

## 6. Set secrets (1 min)

```bash
fly secrets set ALPACA_API_KEY="PKxxxxxxxxxxxxxxxxxxxx" \
                ALPACA_API_SECRET="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" \
                JWT_SECRET="$(openssl rand -hex 32)"
```

Or on Windows PowerShell where `openssl` may not be present:

```powershell
$bytes = [byte[]]::new(32); [Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
$jwt = -join ($bytes | ForEach-Object { "{0:x2}" -f $_ })

fly secrets set ALPACA_API_KEY="PKxxxxxxxxxxxxxxxxxxxx" `
                ALPACA_API_SECRET="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" `
                JWT_SECRET="$jwt"
```

These are stored encrypted on Fly's side and injected into the container at
runtime. They never appear in logs, in git, or in build artifacts.

Verify they are set (values are masked):

```bash
fly secrets list
```

---

## 7. Create the persistent volume (1 min)

```bash
fly volumes create data --size 1 --region iad
```

This is the `/data` mount referenced in `fly.toml`. 1 GB is overkill but it's
the minimum size Fly allows and still costs almost nothing ($0.15/mo).

The volume holds:
- `/data/KILL_SWITCH` (if you ever engage the kill switch — see below)
- Audit logs if you wire up Postgres later
- Optional trained model artifacts under `/data/registry/`

---

## 8. Deploy (3-5 min on first deploy, 1-2 min on subsequent)

```bash
fly deploy
```

This builds the Docker image (via the Worker Dockerfile), pushes it to Fly's
registry, and starts the machine. Watch for:

```
==> Verifying app config
==> Building image
==> Pushing image
==> Creating release
==> Monitoring deployment
1 desired, 1 placed, 1 healthy, 0 unhealthy
```

If you see `1 healthy`, you're live.

---

## 9. Verify it's running

```bash
fly logs
```

Expected within a minute:

```
[mode] paper trading — no real money will be moved.
[profile] conservative: Long-only, mostly cash...
[broker] alpaca (paper=True)
[universe] 16 symbols: AAPL MSFT GOOGL AMZN NVDA META TSLA JPM...
[scheduler] waiting for next US market close. Ctrl-C to stop.
scheduler.start profile=conservative
scheduler.waiting next_run=... wait_minutes=...
```

If the market is currently open and within ~5 minutes of close, it will run a
cycle immediately. Otherwise it sleeps until the next close.

Check Alpaca's web UI to see any orders submitted:
<https://app.alpaca.markets/paper/dashboard/overview>

---

## 10. Day-to-day operations

```bash
# Tail logs in real time
fly logs

# Check machine status
fly status

# Restart (e.g. after changing fly.toml WORKER_ARGS to change profile)
fly deploy

# Connect a shell to inspect /data (rare; logs usually suffice)
fly ssh console

# STOP TRADING immediately — kill switch via volume file
fly ssh console -C "touch /data/KILL_SWITCH"

# Resume trading
fly ssh console -C "rm -f /data/KILL_SWITCH"

# Tear down completely
fly apps destroy stock-market-daemon    # or your app name
```

---

## 11. Change the risk profile after deploy

Edit `fly.toml`:

```toml
[env]
  WORKER_ARGS = "--profile balanced"     # or "--profile aggressive"
```

Then:

```bash
fly deploy
```

The new machine picks up the change on the next restart (a few seconds).

---

## 12. Future: change the symbol universe

The default universe lives in `scripts/run_daemon.py` (`DEFAULT_UNIVERSE` constant).
To change it on the deployed daemon, edit that constant, push to git, and run
`fly deploy` again. Or pass `--universe AAPL MSFT GOOG` via `WORKER_ARGS` in
`fly.toml` to override without code changes.

---

## 13. The cost reality

| Resource | Spec | Monthly |
|---|---|---|
| shared-cpu-1x machine, 512MB | Always-on | ~$3.00 |
| 1 GB volume | | $0.15 |
| Outbound bandwidth | ~10 MB/day | negligible |
| **Total** | | **~$3.15** |
| Fly free credit | | -$5.00 |
| **Net out of pocket** | | **$0** |

If you scale up (more memory for ML inference, multiple regions, etc.) you may
exceed the $5 credit. Run `fly dashboard` to see usage and projected billing.

---

## 14. Things to NEVER do on this deploy

- **Never** set `LIVE_TRADING_ENABLED=true` via `fly secrets set` until you have
  90+ days of paper-trading evidence AND have read [docs/RISK_POLICY.md](RISK_POLICY.md)
  end to end. The system itself will refuse, but don't even try.
- **Never** commit Alpaca keys to git. They go through `fly secrets set`.
- **Never** turn off the kill switch path. It's your emergency stop.
- **Never** ignore the `fly logs` stream for >7 days. Even a passive paper
  system can drift; spot-check what it's doing.

---

## 15. Optional: auto-deploy on every git push

The repo has `.github/workflows/ci.yml` for tests. Add a deploy workflow at
`.github/workflows/deploy.yml` (template included below) to auto-deploy when
you push to `main`. You need to add `FLY_API_TOKEN` as a GitHub secret first:

```bash
fly tokens create deploy --expiry 8760h     # 1 year, copy the output
# Then on github.com → your repo → Settings → Secrets → New repository secret
# Name: FLY_API_TOKEN, value: paste the token
```

The workflow file is at `.github/workflows/deploy.yml`. Already in the repo.

---

## Troubleshooting

**"app name already taken"** — change the `app = "..."` line in `fly.toml` to
something unique before `fly launch`.

**"Volume not found" on deploy** — you forgot Step 7. Run
`fly volumes create data --size 1 --region iad`.

**Logs say "AlpacaBroker requires ALPACA_API_KEY..."** — secrets not set. Run
Step 6 again, then `fly deploy`.

**Machine keeps restarting** — check `fly logs` for the Python traceback. Most
common cause is a missing env var or a typo in the Alpaca keys. Fix and redeploy.

**Daemon log says `[scheduler] waiting...` and never fires** — that's expected
outside market hours. The system fires once per market close (4:00 PM ET on
weekdays, skipping holidays). If you want to test the cycle without waiting,
SSH in and run it once manually:

```bash
fly ssh console -C "python scripts/run_daemon.py --run-once --profile conservative"
```
