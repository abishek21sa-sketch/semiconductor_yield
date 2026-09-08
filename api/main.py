"""
FastAPI backend for the Fab Yield & Capacity Decision Intelligence workspace.
Every /api/* route returns numbers computed by the pipeline modules from real
data (SECOM sensors, the published SMT2020 fab benchmark) -- nothing here is
a hard-coded placeholder.
"""
import logging
import math
import sys
import threading
import time
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import yield_model, scenarios, fab_data, capacity_plan, bottleneck_scheduler, wafer_cnn  # noqa: E402
from api import db  # noqa: E402
from api.auth import require_api_key  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
FRONTEND_DIST = BASE / "frontend" / "dist"

if not (FRONTEND_DIST / "index.html").exists():
    raise RuntimeError(
        "frontend/dist is missing -- the React frontend hasn't been built. Run:\n"
        "  cd frontend && npm install && npm run build\n"
        "(RUN_DEMO.cmd and the Dockerfile do this automatically; see DEPLOYMENT.md.)"
    )

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("fab_app")

_warm_status = {"yield": False, "scenarios": {}, "capacity_plan": False, "bottleneck_dispatch": False,
                 "wafer_defects": False, "error": None}


def _sanitize(obj):
    """Recursively replace non-finite floats (inf/-inf/NaN) with None so the
    payload is valid JSON -- these appear legitimately, e.g. an overloaded
    station's Kingman queue-wait time is mathematically infinite."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    return obj


def _record(run_type, run_key, result, summary_keys):
    """Best-effort persistence of a headline summary of a result -- never
    lets a DB problem take down a request that already computed real data."""
    try:
        summary = {k: result[k] for k in summary_keys if k in result}
        db.record_run(run_type, run_key, result.get("status", "n/a"), summary)
    except Exception:
        log.exception("Failed to record %s/%s to history (non-fatal)", run_type, run_key)


def _warm_cache():
    try:
        log.info("Pre-warming yield model on real SECOM data...")
        y = yield_model.run_full_analysis()
        _record("yield", "default", {"status": "optimal", **y["model"], **y["meta"]},
                ["status", "roc_auc", "pr_auc", "yield_rate", "n_lots"])
        _warm_status["yield"] = True
        log.info("Yield model ready.")
        for s in scenarios.SCENARIOS:
            log.info("Pre-warming scenario '%s' (simulation + Gurobi)...", s)
            r = scenarios.run_scenario(s)
            _record("scenario", s, {"status": "optimal", "bottleneck": r["capacity"]["bottleneck"],
                                     "recommendation_count": len(r["recommendation"])},
                    ["status", "bottleneck", "recommendation_count"])
            _warm_status["scenarios"][s] = True
        log.info("Pre-warming multi-period stochastic capacity plan (large Gurobi MILP)...")
        plan = capacity_plan.run_default_plan()
        _record("capacity_plan", "default", plan, ["status", "n_variables", "n_constraints", "total_backlog_final_week"])
        _warm_status["capacity_plan"] = True
        log.info("Pre-warming bottleneck dispatch scheduler (batch formation + parallel-machine MILP)...")
        dispatch = bottleneck_scheduler.run_default_dispatch()
        _record("bottleneck_dispatch", "default", dispatch,
                ["status", "n_variables", "total_weighted_tardiness_hours"])
        _warm_status["bottleneck_dispatch"] = True
        log.info("Loading wafer defect CNN artifacts (train-once-serve-many; never trains here)...")
        wafer = wafer_cnn.load_artifacts()
        _record("wafer_defects", "default", wafer, ["status", "test_macro_f1", "test_accuracy", "n_labeled_total"])
        _warm_status["wafer_defects"] = True
        log.info("All scenarios warm. Pipeline fully ready.")
    except Exception:
        _warm_status["error"] = traceback.format_exc()
        log.exception("Pipeline warm-up failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Ensuring database schema (Alembic migrations)...")
    db.ensure_schema()  # synchronous: must finish before any request can hit /api/history
    threading.Thread(target=_warm_cache, daemon=True).start()
    yield


app = FastAPI(title="Fab Yield & Capacity Decision Intelligence", lifespan=lifespan)

app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="frontend-assets")

# All /api/* routes require X-API-Key when the API_KEY env var is set;
# disabled (open) by default so local/demo use needs zero setup -- see
# api/auth.py and SECURITY.md.
api = APIRouter(prefix="/api", dependencies=[Depends(require_api_key)])


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.monotonic()
    try:
        response = await call_next(request)
    except Exception:
        log.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"error": "internal_server_error", "path": request.url.path},
        )
    elapsed_ms = (time.monotonic() - start) * 1000
    log.info("%s %s -> %d (%.0fms)", request.method, request.url.path, response.status_code, elapsed_ms)
    return response


@app.get("/api/health")
def health():
    """Liveness probe -- always returns 200 if the process is up, regardless
    of whether the real-data pipeline has finished warming, and unauthenticated
    even when API_KEY is set (Docker's HEALTHCHECK has no key)."""
    return {"status": "ok"}


@api.get("/status")
def status():
    """Business readiness -- whether the real-data pipeline has finished
    pre-warming (yield model + all scenarios)."""
    return _warm_status


@api.get("/history")
def get_history(run_type: str | None = None, limit: int = 50):
    """Real persisted run history -- rows a prior request actually wrote to
    the database (SQLite locally, Postgres in Docker), not synthesized."""
    return JSONResponse(db.get_history(run_type=run_type, limit=min(limit, 200)))


@api.get("/yield")
def get_yield():
    try:
        result = yield_model.run_full_analysis()
        return JSONResponse(_sanitize(result))
    except FileNotFoundError as e:
        log.error("SECOM data missing: %s", e)
        raise HTTPException(503, "Real SECOM data files are missing -- see data/README or DEPLOYMENT.md.")


@api.get("/yield/theory")
def get_yield_theory(defect_density: float = 0.5, cluster_alpha: float = 2.0):
    if defect_density < 0 or cluster_alpha <= 0:
        raise HTTPException(400, "defect_density must be >= 0 and cluster_alpha must be > 0")
    die_areas = [round(0.05 + i * 0.05, 2) for i in range(40)]
    return JSONResponse(yield_model.yield_model_curve(die_areas, defect_density, cluster_alpha))


@api.get("/scenarios")
def list_scenarios():
    return JSONResponse(scenarios.list_scenarios())


@api.get("/scenario/{name}")
def get_scenario(name: str):
    if name not in scenarios.SCENARIOS:
        raise HTTPException(404, f"unknown scenario '{name}'. Valid: {list(scenarios.SCENARIOS)}")
    result = scenarios.run_scenario(name)
    _record("scenario", name, {"status": "optimal", "bottleneck": result["capacity"]["bottleneck"],
                                "recommendation_count": len(result["recommendation"])},
            ["status", "bottleneck", "recommendation_count"])
    return JSONResponse(_sanitize(result))


@api.get("/capacity_plan")
def get_capacity_plan():
    """Large-scale two-stage stochastic multi-period MILP (thousands of
    variables/constraints -- see pipeline/capacity_plan.py) that genuinely
    needs a real Gurobi license, unlike the small single-week release mix in
    /api/scenario/*."""
    result = capacity_plan.run_default_plan()
    return JSONResponse(_sanitize(result))


@api.get("/bottleneck_dispatch")
def get_bottleneck_dispatch():
    """Exact bottleneck dispatch scheduler: real batch formation (Diffusion)
    + parallel-machine sequencing (Dry_Etch), minimizing weighted tardiness
    against real due dates. The tractable, exact complement to the
    heuristic-but-full-scope SimPy simulation -- see pipeline/
    bottleneck_scheduler.py for why full-fab exact scheduling is
    combinatorially intractable at real fab scale."""
    result = bottleneck_scheduler.run_default_dispatch()
    return JSONResponse(_sanitize(result))


@api.get("/wafer_defects")
def get_wafer_defects():
    """Real CNN classifier over real WM-811K wafer defect-map images
    (172,950 human-labeled real wafers, 9 classes) -- see pipeline/
    wafer_cnn.py. Train-once-serve-many: this loads a pre-trained model's
    saved metrics and never trains on request. Returns {"status":
    "not_trained", ...} if scripts/train_wafer_cnn.py hasn't been run on
    this machine (the raw ~2GB dataset isn't in git -- see
    data/wm811k/ATTRIBUTION.md)."""
    result = wafer_cnn.load_artifacts()
    return JSONResponse(_sanitize(result))


@api.get("/topology")
def get_topology():
    """Raw real topology so the frontend can recompute utilization live as the
    visitor drags a tool-count slider -- same formula as pipeline/capacity.py,
    evaluated client-side for instant feedback (no round trip per drag)."""
    stations = fab_data.load_station_groups()
    route_ids = scenarios.ROUTE_IDS
    routes = {}
    route_totals = {}
    route_step_counts = {}
    for rid in route_ids:
        steps = fab_data.load_route(rid)
        by_group = steps.groupby("stngrp")["mean_ptime_min"].sum().to_dict()
        routes[rid] = by_group
        route_totals[rid] = float(steps["mean_ptime_min"].sum())
        route_step_counts[rid] = int(len(steps))
    demand = fab_data.load_demand()
    return JSONResponse(_sanitize({
        "stations": {
            g: {
                "n_tools": float(row["n_tools"]),
                "availability": float(row["availability"]),
            }
            for g, row in stations.iterrows() if not g.startswith("Delay")
        },
        "routes": routes,
        "route_totals": route_totals,
        "route_step_counts": route_step_counts,
        "route_ids": route_ids,
        "demand": {
            rid: float(demand.loc[rid, "weekly_demand_lots"]) if rid in demand.index else None
            for rid in route_ids
        },
    }))


app.include_router(api)


@app.get("/{full_path:path}")
def spa(full_path: str):
    """Serves the built React app for '/' and every client-side route (e.g.
    '/methodology') so a direct navigation or page refresh works -- React
    Router takes over from there. Registered last so it never shadows an
    /api/* route or /assets/* static file above."""
    return FileResponse(FRONTEND_DIST / "index.html")
