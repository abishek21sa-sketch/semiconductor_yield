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

First load takes ~30-90s while the server pre-warms the full real-data pipeline (the SECOM yield model, all four Quick Scenarios, the multi-period stochastic capacity plan, the bottleneck dispatch scheduler, the wafer defect CNN's saved metrics, the LVHM-vs-HVLM archetype comparison, and the cross-pipeline integration + impact summary) in a background thread. Poll `/api/status` or watch the badge in the top-right of the page.

## Wafer defect CNN + baseline (optional, one-time)

`/api/wafer_defects`, `/api/wafer_defects_baseline`, and (partially) `/api/integration`/`/api/impact_summary` need a trained model, which is **not** built automatically (unlike everything else in this app) because it needs a ~2GB dataset that isn't bundled and takes real minutes to train on CPU:

```bash
# 1. Download WM-811K's LSWMD.pkl from Kaggle (see data/wm811k/ATTRIBUTION.md)
#    and place it at data/wm811k/LSWMD.pkl

# 2. Train the CNN + the hand-engineered-feature baseline (one-time, ~15-20 min on CPU, no GPU needed)
.venv\Scripts\python scripts\train_wafer_cnn.py

# Other useful flags:
#   --smoke-test      fast correctness check on a tiny subset (writes to a throwaway temp dir)
#   --cnn-only        skip the baseline (e.g. re-running after a CNN-only code change)
#   --baseline-only   skip the CNN
```

This writes `data/wm811k/wafer_cnn_{model.pt,metrics.json,samples.json}` and `wafer_baseline_metrics.json` (all gitignored, all local-only). Once they exist, the API loads them instantly on every server startup -- it never re-trains. Without them, the relevant endpoints return `{"status": "not_trained", ...}` instead of failing (and `/api/integration`/`/api/impact_summary` degrade the wafer-dependent fields to `null` rather than failing outright), exactly like the license-gated MILPs report `license_required` without a Gurobi license -- same graceful-degradation pattern, different missing prerequisite.

## Real fab archetype comparison

`/api/archetype_comparison` compares the real SMT2020 LVHM (10 products, `data/smt2020_lvhm/`) and HVLM (2 products, `data/smt2020_hvlm/`) configurations -- both are bundled in the repo (unlike WM-811K, they're small, ~660KB total), so this needs no setup and works out of the box.

`scripts/train_wafer_cnn.py --smoke-test` runs a fast 1-epoch/2000-sample correctness check (writes to a throwaway temp directory, never touches the real artifacts above) -- useful to confirm the pipeline runs end to end before committing to a full run.

## Docker

```bash
docker compose up --build
```

Serves at `http://localhost:8020`, with a `db` (Postgres 16) service alongside `fab-app` -- `docker-compose.yml` wires `DATABASE_URL` so the container talks to Postgres instead of a local SQLite file; the exact same SQLAlchemy models and Alembic migrations run against either backend.

The `Dockerfile` is a multi-stage build: a `node:22-slim` stage runs `npm ci && npm run build` for the React frontend, and only its `dist/` output is copied into the final Python image -- Node itself isn't part of the runtime image.

Runs with no Gurobi license mounted by default. The single-week release-mix MILP (`pipeline/release_optimizer.py`, ~10 variables) is well inside Gurobi's bundled size-limited free tier (2000 vars/constraints) and solves correctly unlicensed. The two larger models -- the multi-period stochastic capacity plan (`pipeline/capacity_plan.py`, ~3,400 variables at the default 10-product scale) and the bottleneck dispatch scheduler (`pipeline/bottleneck_scheduler.py`, tens of thousands of variables) -- exceed that free tier and need a real academic/commercial license; without one they report `{"status": "license_required", "n_variables": ..., ...}` instead of crashing. To use a real license, place it at `./gurobi.lic` (already gitignored) and uncomment the `volumes`/`environment` lines under `fab-app` in `docker-compose.yml`.

`docker build -t fab-app .` / `docker run -p 8020:8020 fab-app` works the same way without compose (falls back to local SQLite inside the container, since there's no `db` service without compose).

## Render

`render.yaml` is a Render Blueprint for a single Docker web service built from the existing `Dockerfile` -- no separate managed database, no second service. This file has not been deployed against a real Render account as part of authoring it; there were no deploy credentials available to do so, so treat the following as documented intent, not a verified deploy.

To use it: push this repo to GitHub/GitLab, then in the Render dashboard choose **New +** -> **Blueprint** and point it at the repo (Render reads `render.yaml` automatically), or **New +** -> **Web Service** and pick **Docker** manually and ignore the file.

- **Port:** Render injects its own `$PORT` env var into the container at start time (it does not honor the Dockerfile's `EXPOSE`). The Dockerfile's `CMD` was changed from a hardcoded `--port 8020` to `uvicorn ... --port ${PORT:-8020}` (shell form, so the env var actually expands) specifically so the same image works unchanged on Render *and* locally -- `docker-compose.yml` and a bare `docker run` never set `PORT`, so they keep using 8020 exactly as before.
- **Health check:** `render.yaml` sets `healthCheckPath: /api/health`, the same liveness probe Docker's own `HEALTHCHECK` polls -- it returns `{"status": "ok"}` immediately regardless of pipeline warm-up state and is never behind `API_KEY`.
- **Persistence:** `DATABASE_URL` is left unset by default, so `/api/history` runs against SQLite on the container's own filesystem -- fine for a demo, but Render's free plan has no persistent disk, so that history resets on every redeploy or restart. Point `DATABASE_URL` at a real Postgres connection string (Render's own managed Postgres, or any external one) if run history needs to survive restarts; the same SQLAlchemy models and Alembic migrations run against either backend with no code change.
- **Gurobi-licensed features report `license_required`, same as locally without a license.** `pipeline/capacity_plan.py`'s multi-period stochastic plan and `pipeline/bottleneck_scheduler.py`'s dispatch scheduler both build MILPs past Gurobi's bundled free-tier limit (2000 vars/constraints); without `GRB_LICENSE_FILE` set they degrade to `{"status": "license_required", "n_variables": ..., ...}` exactly as documented above for Docker -- a free Render deploy behaves identically to an unlicensed local run, it doesn't lose functionality relative to that baseline. There's no mounted-volume equivalent of `docker-compose.yml`'s `gurobi.lic` mount on Render's free plan; a real license there would need Render's paid "Secret Files" feature or a Gurobi Cloud/token-based license instead of a mounted file.
- **Memory:** the full pipeline warm-up loads pandas/scikit-learn/PyTorch, trains a 400-tree Random Forest via 5-fold CV, runs SimPy Monte Carlo replications, and builds Gurobi models, all in one process (see api/main.py's `_warm_cache`) -- this is real CPU/RAM work, not a placeholder, and may be tight against Render's free-plan 512MB instance. If warm-up crashes or the process is OOM-killed, that's a plan-sizing issue, not a code bug; a paid Render plan with more memory is the fix, not a smaller model.
- **Wafer defect CNN:** `data/wm811k/` (the ~2GB WM-811K raw file and trained CNN/baseline artifacts) is gitignored and dockerignored, so it's never baked into the image or a Render build -- `/api/wafer_defects` reports `{"status": "not_trained", ...}` on a fresh Render deploy exactly as it does on a fresh local clone, until those artifacts are trained and shipped some other way.

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
