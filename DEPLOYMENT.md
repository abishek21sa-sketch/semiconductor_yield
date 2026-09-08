# Deployment

## Local (no Docker)

Requires Python 3.12+ and Node.js 22+ (for building the React frontend once; the built output is static files, no Node needed at runtime).

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt      # Windows
# .venv/bin/pip install -r requirements.txt        # macOS/Linux

cd frontend
npm ci
npm run build                                       # builds frontend/dist/ -- required before starting the server
cd ..

.venv\Scripts\python -m uvicorn api.main:app --host 127.0.0.1 --port 8020
```

`api/main.py` checks for `frontend/dist/index.html` at import time and raises a clear error telling you to build it if it's missing, rather than failing on the first request.

Or just double-click `RUN_DEMO.cmd` on Windows, which builds the frontend automatically if `frontend/dist` doesn't exist yet, then starts the server and opens the browser for you.

On startup the app runs its Alembic migrations automatically (`api/db.py`'s `ensure_schema()`, called synchronously in the FastAPI `lifespan` before anything can serve `/api/history`), creating `fab_app.db` (SQLite) in the project root if it doesn't exist yet. No manual migration step is needed for local use. If you want to run migrations by hand instead (e.g. to inspect what would change):

```bash
.venv\Scripts\alembic upgrade head
.venv\Scripts\alembic revision --autogenerate -m "description"   # after changing a model in api/db.py
```

First load takes ~30-90s while the server pre-warms the full real-data pipeline (the SECOM yield model, all four Quick Scenarios, the multi-period stochastic capacity plan, the bottleneck dispatch scheduler, and loading the wafer defect CNN's saved metrics) in a background thread. Poll `/api/status` or watch the badge in the top-right of the page.

## Wafer defect CNN (optional, one-time)

`/api/wafer_defects` needs a trained model, which is **not** built automatically (unlike everything else in this app) because it needs a ~2GB dataset that isn't bundled and takes real minutes to train on CPU:

```bash
# 1. Download WM-811K's LSWMD.pkl from Kaggle (see data/wm811k/ATTRIBUTION.md)
#    and place it at data/wm811k/LSWMD.pkl

# 2. Train (one-time, ~15 min on CPU, no GPU needed)
.venv\Scripts\python scripts\train_wafer_cnn.py
```

This writes `data/wm811k/wafer_cnn_{model.pt,metrics.json,samples.json}` (all gitignored, all local-only). Once they exist, `/api/wafer_defects` loads them instantly on every server startup -- it never re-trains. Without them, the endpoint returns `{"status": "not_trained", ...}` instead of failing, exactly like the license-gated MILPs report `license_required` without a Gurobi license -- same graceful-degradation pattern, different missing prerequisite.

`scripts/train_wafer_cnn.py --smoke-test` runs a fast 1-epoch/2000-sample correctness check (writes to a throwaway temp directory, never touches the real artifacts above) -- useful to confirm the pipeline runs end to end before committing to a full run.

## Docker

```bash
docker compose up --build
```

Serves at `http://localhost:8020`, with a `db` (Postgres 16) service alongside `fab-app` -- `docker-compose.yml` wires `DATABASE_URL` so the container talks to Postgres instead of a local SQLite file; the exact same SQLAlchemy models and Alembic migrations run against either backend.

The `Dockerfile` is a multi-stage build: a `node:22-slim` stage runs `npm ci && npm run build` for the React frontend, and only its `dist/` output is copied into the final Python image -- Node itself isn't part of the runtime image.

Runs with no Gurobi license mounted by default. The single-week release-mix MILP (`pipeline/release_optimizer.py`, ~10 variables) is well inside Gurobi's bundled size-limited free tier (2000 vars/constraints) and solves correctly unlicensed. The two larger models -- the multi-period stochastic capacity plan (`pipeline/capacity_plan.py`, ~3,400 variables at the default 10-product scale) and the bottleneck dispatch scheduler (`pipeline/bottleneck_scheduler.py`, tens of thousands of variables) -- exceed that free tier and need a real academic/commercial license; without one they report `{"status": "license_required", "n_variables": ..., ...}` instead of crashing. To use a real license, place it at `./gurobi.lic` (already gitignored) and uncomment the `volumes`/`environment` lines under `fab-app` in `docker-compose.yml`.

`docker build -t fab-app .` / `docker run -p 8020:8020 fab-app` works the same way without compose (falls back to local SQLite inside the container, since there's no `db` service without compose).

## Environment variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DATABASE_URL` | No | `sqlite:///./fab_app.db` | SQLAlchemy connection string. `docker-compose.yml` sets this to the `db` Postgres service; unset it (or override it) for local SQLite. |
| `API_KEY` | No | unset (auth disabled) | When set, every `/api/*` route requires a matching `X-API-Key` header (see `api/auth.py`). Leave unset for local/demo use with zero setup. |
| `GRB_LICENSE_FILE` | No | unset (bundled free tier) | Path to a real Gurobi license file, only needed to solve the two large MILPs above their free-tier limit. |

Example enabling auth locally:

```bash
API_KEY=change-me .venv/Scripts/python -m uvicorn api.main:app --host 127.0.0.1 --port 8020
curl -H "X-API-Key: change-me" http://127.0.0.1:8020/api/status
```

## Health checks

- `GET /api/health` -- liveness only, returns `{"status": "ok"}` immediately regardless of pipeline warm-up state, and is never behind `API_KEY`. This is what Docker's `HEALTHCHECK` polls.
- `GET /api/status` -- business readiness: whether the real-data pipeline (yield model + all scenarios + capacity plan + dispatch + wafer defect CNN artifacts) has finished pre-warming, and any warm-up error. Behind `API_KEY` when it's set.

## What this is not ready for

This is a portfolio/demo project, not a hardened production service:

- **Single process, no worker pool.** `uvicorn` runs one process; concurrent scenario requests before warm-up finishes will serialize on the same CPU-bound Gurobi/SimPy work. Fine for a demo; not for real concurrent load.
- **One shared API key, not user auth.** `API_KEY` is a single static secret checked on every request -- real access control (per-user identity, scoped permissions, rotation, revocation) would need something like OAuth/JWT with a real identity provider. See `SECURITY.md`.
- **No rate limiting.** Do not expose this to the public internet without adding it.
- **No TLS termination.** Put a reverse proxy (nginx, Caddy, a cloud load balancer) in front if this needs to be internet-facing.
- **No secrets management.** `API_KEY` and `DATABASE_URL` (if it embeds Postgres credentials) should be injected via environment variables or a `.env` file kept out of git, never hardcoded -- `docker-compose.yml`'s default Postgres password (`fab`/`fab`) is a local-dev convenience, not something to reuse anywhere real.

See `SECURITY.md` for the fuller security posture and disclosure notes.
