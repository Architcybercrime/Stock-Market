# Dashboard

A modern, animated, static dashboard for the paper-trading daemon. Built with
Next.js + Three.js + Framer Motion. Auto-deploys to **GitHub Pages** from
the `deploy_pages.yml` workflow. Reads the live portfolio state from
`data/paper_state.json` in this repo via raw.githubusercontent.com.

**Live URL once enabled:** https://architcybercrime.github.io/Stock-Market/

## What it shows

- **Hero**: rotating 3D glass orb behind your current NAV. Color reflects
  total return tone (green/red/neutral).
- **Stats row**: cash, today's Δ (absolute + %), unrealized P&L. All animated.
- **Equity curve**: line chart of historic NAV from `equity_history`.
- **Allocation donut**: SVG donut showing portfolio composition by symbol +
  cash. Animates on load.
- **Holdings grid**: per-position card with qty, weight, avg cost, last
  price, unrealized P&L. Hover lifts each card.
- **Recent trades**: last 12 fills, buy/sell tagged.
- **About panel**: trade frequency, snapshot rhythm, link to commit history.

## How it stays fresh without a server

- The daemon (`daily_trade.yml`) trades on weekdays, commits state changes
  to `data/paper_state.json` with `[skip ci]`.
- The snapshot workflow (`daily_snapshot.yml`) refreshes mark-to-market
  prices twice a day, every day including weekends, also committing.
- The dashboard fetches the file from raw.githubusercontent.com whenever
  someone opens it. There is no server, no database, no API service.
- Every commit to the state file triggers a Pages redeploy via the
  `deploy_pages.yml` workflow.

This means the dashboard is always within ~minutes of the most recent
snapshot.

## One-time setup (you only do this once)

1. Go to <https://github.com/Architcybercrime/Stock-Market/settings/pages>
2. Under **Build and deployment** → **Source**, select **GitHub Actions**
3. Save

That's it. The next push to `main` (or a manual workflow run) will build and
deploy. The URL will appear in the workflow run summary.

## Manual deploy

Actions tab → **Deploy dashboard to GitHub Pages** → Run workflow.

Subsequent deploys happen automatically when:

- Anyone pushes to `frontend/**`
- The state file `data/paper_state.json` changes (triggered by trade or
  snapshot workflows)

## Running it locally

```bash
cd frontend
npm install
npm run dev
# open http://localhost:3000
```

By default the local build reads the same raw GitHub URL. To point at a
local state file instead:

```bash
NEXT_PUBLIC_STATE_URL=/api/state npm run dev
```

(You'd need a separate dev-only proxy for that. The default is fine for most
use — you can always refresh and see the latest committed state.)

## Customization

- **Custom domain**: set repo variable `BASE_PATH` to `""` in
  Settings → Variables, then point your DNS at GitHub Pages and add a CNAME
  in Settings → Pages.
- **Theme colors**: edit `frontend/tailwind.config.ts` — the `accent`,
  `accent2`, `good`, `bad` colors propagate through the whole app.
- **3D orb behavior**: `frontend/components/HeroOrb.tsx` — rotation speed,
  distortion, lighting. Don't crank it; subtle is better on a trading
  dashboard.
- **What stats appear**: `frontend/components/StatsRow.tsx`.
- **Universe / data window**: `scripts/run_daemon.py` (`NSE_UNIVERSE`) — the
  dashboard derives everything from what the daemon traded.

## Performance

- Bundle size: ~500 KB gzipped (Three.js is most of it).
- First paint: 1–2 sec on a fresh load.
- Subsequent navigations: instant (it's a static site).
- The state JSON is typically 50–200 KB.

## Limits

- Pure client-side. No login, no per-user state. The whole repo can see the
  same dashboard. If you want privacy, make the repo private (Pages still
  works for private repos on Pro+ plans, not the Free plan).
- yfinance prices in the snapshot file can be stale up to 12 hours
  (snapshot runs twice daily).
- No interactive trade entry. This is a read-only view by design.
