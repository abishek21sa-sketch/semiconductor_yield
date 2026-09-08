# Fab Yield & Capacity Decision Intelligence Platform

**Evidence boundary:** real SECOM fab sensor data + the published SMT2020 semiconductor-fab benchmark; simulation/optimization results derived from that benchmark, not validated against a named real plant.

## What this is

A decision-intelligence pipeline over two real datasets: it predicts yield risk from real semiconductor process-sensor data, models the real fab's capacity and bottleneck, simulates it stochastically under different dispatch/release policies, and optimizes weekly lot release with a Gurobi MILP against real order-demand data.

```text
REAL FAB SENSOR DATA (SECOM: 1567 lots, 590 sensors, real pass/fail)
                ↓
YIELD-RISK AI — calibrated Random Forest (5-fold CV, out-of-fold, no leakage)
+ classical semiconductor yield theory (Poisson / Murphy / Negative-Binomial)
                ↓
SPC PROCESS MONITORING — 3-sigma band on the top failure-driving sensor
                ↓
REENTRANT FAB DIGITAL TWIN — topology from the published SMT2020 benchmark
(photo/etch/diffusion/CMP reentrant loop, real tool counts, real MTBF/MTTR)
                ↓
CAPACITY / BOTTLENECK ANALYSIS — Little's Law, Kingman G/G/m queueing
                ↓
STOCHASTIC SIMULATION — SimPy discrete-event twin: dispatch rules (FIFO/
Critical Ratio) x release control (uncontrolled vs CONWIP), Monte Carlo
tool-failure + processing-time variability, P95/CVaR tail cycle time
                ↓
GUROBI OPTIMIZATION — finite-capacity weekly lot-release MILP against real
order-demand rates (order.txt), minimum per-product fill-rate commitment
                ↓
MULTI-PERIOD STOCHASTIC PLAN — two-stage Gurobi MILP: 10 products x 26 weeks
of release decisions + recourse over Monte-Carlo capacity scenarios sampled
from real MTBF/MTTR (3,380 vars / 5,990 constraints -- past Gurobi's free-
tier limit, genuinely needs a real license)
                ↓
BOTTLENECK DISPATCH SCHEDULER — exact MILP: real batch formation (Diffusion,
real BATCHMN/BATCHMX) + parallel-machine sequencing (Dry_Etch, 21 real
tools), minimizing weighted tardiness -- the tractable exact complement to
full-fab scheduling, which is combinatorially intractable at real scale
(~180K variables) and is why fab_twin.py's simulation exists instead
                ↓
EXPLAINABLE RECOMMENDATION — evidence-labeled per-scenario brief
```

Run it: double-click `RUN_DEMO.cmd` (builds the React frontend on first run if needed, then starts the API server), or `docker compose up --build` (multi-stage build: Node builds the frontend, then it's copied into the Python image). First load takes ~30-90s while the server pre-computes all four Quick Scenarios (across all 10 real products) plus the two large MILPs in the background; the workspace opens at `http://127.0.0.1:8020`, with a dedicated methodology page at `/methodology`. See `DEPLOYMENT.md` for details.

## The data

- **SECOM** (UCI ML Repository #179) — 1567 real production lots from a live semiconductor fab, 590 real anonymized process-sensor signals per lot, real pass/fail line-test outcome, real timestamps. `data/secom.data` / `data/secom_labels.data`.
- **SMT2020** (Kopp, Hassoun, Kalir & Mönch, *IEEE Trans. Semiconductor Manufacturing*, 2020) — the standard published academic benchmark for reentrant wafer-fab simulation research (successor to the classic MIMAC benchmark family). **All 10 real products** from the LVHM (Low-Volume-High-Mix) archetype fab are modeled, each with its own real route (300-500+ reentrant process steps), real tool-group counts, real MTBF/MTTR reliability data, and real order/demand rates. Official distribution: <https://p2schedgen.fernuni-hagen.de/index.php/downloads/simulation>. Obtained here via the open research artifact `PySCFabSim-revised` (Zenodo record 15088815). See `data/smt2020_lvhm/ATTRIBUTION.md`.

## What this is not

- SMT2020 is a **published academic benchmark** representing realistic fab characteristics (a "Low-Volume-High-Mix" archetype fab) — it is not proprietary data from a named real company's fab, and nothing here is validated against an actual plant.
- Station groups are aggregated from the benchmark's ~100 individual tool sub-families to a 12-group level (`pipeline/fab_data.py: classify_stngrp`) for tractability. This is a stated modeling choice, not the benchmark's native resolution.
- The Gurobi release-mix optimization uses a minimum-fill-rate floor (default 2% of real weekly demand per product, across all 10 products) to model a plausible contractual service commitment — real demand in this benchmark (~390 lots/week across 10 products) vastly exceeds what the real bottleneck (Diffusion, 10 furnaces) can supply, so the floor is what forces a realistic multi-product mix instead of a degenerate single-product solution. This assumption is explicit in `pipeline/release_optimizer.py`, not hidden.
- The SimPy simulation's steady-state metrics (mean/P95 cycle time) are reported over a fixed 30-day window with a 3-day warm-up; under an overloaded scenario (utilization > 1) the queue is genuinely unstable, so these numbers are a transient snapshot, not a converged steady state. The Kingman queueing approximation is standard textbook theory (VUT equation), not fit to any data.

## Project layout

```
pipeline/
  yield_model.py        SECOM data load/clean, cross-validated RF classifier, SPC, classical yield theory
  fab_data.py            SMT2020 raw-file parsing -> station-group topology, real demand
  capacity.py             Little's Law, Kingman G/G/m, station utilization / bottleneck detection
  fab_twin.py              SimPy discrete-event simulation (dispatch rules, CONWIP, Monte Carlo)
  release_optimizer.py     Gurobi MILP: capacity-constrained weekly release mix (~10 vars -- small on purpose)
  capacity_plan.py         Two-stage stochastic Gurobi MILP: 10 products x 26 weeks + Monte Carlo
                          capacity recourse (3,380 vars / 5,990 constraints -- exceeds Gurobi's free tier)
  bottleneck_scheduler.py  Exact batch-formation + parallel-machine dispatch MILP at the real
                          bottlenecks (Diffusion, Dry_Etch) -- tractable complement to full-fab scheduling
  scenarios.py             Composes the above into 4 named Quick Scenarios + recommendation text
api/main.py               FastAPI backend: structured logging, request-timing middleware,
                          liveness (/api/health) vs readiness (/api/status), pre-warms at startup
api/db.py                 SQLAlchemy models + engine (SQLite locally, Postgres in Docker via
                          DATABASE_URL) -- /api/history reads back real persisted run records
api/auth.py               API-key dependency for /api/* -- open by default, real when API_KEY is set
alembic/, alembic.ini     Schema migrations for api/db.py's models (run automatically at startup,
                          or by hand with `alembic upgrade head`)
frontend/                 React (Vite) UI -- api/main.py serves the built frontend/dist/, mounting
                          /assets and falling back to index.html for client-side routes so
                          React Router's /methodology page works on direct navigation/refresh
  src/pages/Workspace.jsx   The live dashboard: hero stats, pipeline diagram, scenario nav,
                          What-If panel (client-side recompute), all 8 result cards
  src/pages/Methodology.jsx Dedicated methodology page -- what's real, what's modeled, and why
  src/components/           One component per card/chart (BarRow, SvgLineChart, SPCChart, etc.)
tests/                    Unit tests for the deterministic math + FastAPI integration tests
data/                     SECOM + SMT2020 raw files (see ATTRIBUTION.md)
Dockerfile, docker-compose.yml   Containerized run: app + Postgres (see DEPLOYMENT.md)
.github/workflows/tests.yml      CI: runs the full test suite on every push/PR
LICENSE, SECURITY.md, DEPLOYMENT.md
```

## Testing & CI

`pytest tests/ -v` runs 38 tests: unit tests on the deterministic math (Little's Law, Kingman -- verified exact against the M/M/1 formula, classical yield theory), unit tests on the multi-period stochastic plan (backlog accounting consistency, the cumulative floor, and -- the whole point of that module -- a test that asserts it genuinely exceeds Gurobi's 2000-variable free-tier limit), unit tests on the bottleneck dispatch scheduler (no capacity violations, no jobs starting before their lots arrive, real batch-size bounds respected, tardiness actually emerges under realistic load), plus FastAPI integration tests hitting every real endpoint including `/api/history`, the React Router SPA fallback (`/methodology` served without a matching backend route), and the built JS bundle actually being reachable under `/assets` (`tests/test_api.py`). CI (`.github/workflows/tests.yml`) builds the React frontend with Node before running pytest, since `api/main.py` refuses to start without a built `frontend/dist/`. It passes unlicensed, since `release_optimizer.py`'s small MILP fits Gurobi's free tier even though `capacity_plan.py`'s and `bottleneck_scheduler.py`'s don't (CI has no Gurobi license configured, so those modules' own size-limit tests accept either `optimal` or the graceful `license_required` fallback, and only prove the solve itself when run with a real license, as it is locally).

## Talking points

See `TALKING_POINTS.md` for a one-page cheat sheet on the dataset, method, and results.
