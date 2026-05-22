# Frontend (Next.js 14, App Router)

Institutional dashboard. Authenticates against the FastAPI backend, polls
portfolio/risk/signals endpoints with SWR, and surfaces operator controls
(kill switch, circuit-breaker reset).

## Local dev

Requires Node 20+. Backend should be running on `http://localhost:8000`.

```bash
cd frontend
npm install
npm run dev
# open http://localhost:3000
```

Default scaffold creds: `viewer / viewer` or `operator / operator`. Operator
endpoints (kill switch, breaker reset) require the operator role.

## Pages

- `/` Dashboard — NAV, P&L, positions, risk gauge.
- `/risk` Risk console — engage/release kill switch, reset breaker, view limits.
- `/signals` Signal feed — most recent aggregator output.

## Configuration

`NEXT_PUBLIC_API_URL` controls the backend URL used by `next.config.js`
rewrites (default `http://localhost:8000`).
