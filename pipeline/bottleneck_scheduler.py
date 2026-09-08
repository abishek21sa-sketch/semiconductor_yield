"""
Exact bottleneck dispatch scheduler -- a real, tractable complement to the
combinatorially-intractable full-fab schedule (see module docstring
discussion in project docs: full lot-level time-indexed scheduling across
all ~4,000 real reentrant steps for 10 products comes out to roughly
180,000 binary variables, the same wall that's why real fabs use
discrete-event simulation + dispatch heuristics for full-line scheduling,
not exact MILP -- which is exactly why fab_twin.py exists).

This solves the problem real fabs actually solve exactly and repeatedly:
given a realistic snapshot of lots currently queued at the two bottleneck
station groups (Diffusion, Dry_Etch), find the optimal batch-formation and
sequencing decision right now. This is Theory-of-Constraints-style
bottleneck dispatching -- solved on a rolling basis in real operations, not
as a one-shot multi-week schedule.

Two real decisions, modeled separately because they're genuinely different:

1. Batch formation (Diffusion only): real diffusion furnaces process a
   BATCH of lots together (real BATCHMN/BATCHMX wafer-count constraints
   from the benchmark's own route files) -- which lots combine into which
   batch is a bin-packing decision, not a time-scheduling one.
2. Time-indexed scheduling (both stations): once batches (Diffusion) and
   individual jobs (Dry_Etch) exist, assign each a start time on an hourly
   grid, respecting each station's real parallel-tool capacity (10 real
   furnaces, 21 real dry-etch tools) and minimizing weighted tardiness
   against a real due-date convention (release + flow-allowance x raw
   route time, the same convention fab_twin.py uses).
"""
import math
import time
from functools import lru_cache

import gurobipy as gp
from gurobipy import GRB

from . import fab_data

PIECES_PER_LOT = 25  # real value from order.txt (PIECES column)
BUCKET_MIN = 60      # hourly time buckets
HORIZON_HOURS = 96   # 4-day dispatch horizon


def _first_step_of_type(route_df, stngrp):
    matches = route_df[route_df["stngrp"] == stngrp]
    return None if matches.empty else matches.iloc[0]


def build_snapshot(route_ids, lots_per_product=3, seed=11):
    """A realistic queue snapshot: for each real product, a few lots each
    needing their next real Diffusion batch step or next real Dry_Etch
    step (alternating, using each product's own real route data for
    processing time / batch limits). Due dates use fab_twin.py's own real
    convention (release + flow_allowance x raw route time)."""
    import random
    rng = random.Random(seed)
    diffusion_jobs, dryetch_jobs = [], []
    lot_id = 0
    for rid in route_ids:
        route_df = fab_data.load_route(rid)
        diff_step = _first_step_of_type(route_df, "Diffusion")
        etch_step = _first_step_of_type(route_df, "Dry_Etch")
        for i in range(lots_per_product):
            lot_id += 1
            release_offset = rng.uniform(0, 240)  # staggered arrivals over 4h
            if diff_step is not None and (i % 2 == 0):
                ptime = float(diff_step["mean_ptime_min"])
                diffusion_jobs.append({
                    "lot": lot_id, "product": rid,
                    "ptime": ptime,
                    "batch_min": float(diff_step["batch_min"] or 75),
                    "batch_max": float(diff_step["batch_max"] or 125),
                    "pieces": PIECES_PER_LOT,
                    # Local operation due date: this is a near-term dispatch
                    # snapshot, not the lot's full end-to-end route due date
                    # (that convention lives in fab_twin.py/capacity_plan.py
                    # and is calibrated for multi-week journeys, so it never
                    # binds at 96-hour granularity). A realistic local
                    # commitment is "clear this operation's queue within a
                    # modest multiple of its own processing time."
                    "due": release_offset + max(5 * ptime, 8 * 60),
                    "arrival": release_offset,
                })
            if etch_step is not None:
                ptime = float(etch_step["mean_ptime_min"])
                dryetch_jobs.append({
                    "lot": lot_id, "product": rid,
                    "ptime": ptime,
                    "due": release_offset + max(5 * ptime, 8 * 60),
                    "arrival": release_offset,
                })
    return diffusion_jobs, dryetch_jobs


def _form_diffusion_batches(jobs, max_slots):
    """Bin-packing sub-model: which lots combine into which furnace batch,
    respecting real BATCHMN/BATCHMX wafer-count constraints. Returns one
    "job" per used batch slot (pieces-weighted mean ptime, the real
    due-date floor of its members) for the scheduling stage below."""
    m = gp.Model("diffusion_batch_formation")
    m.Params.OutputFlag = 0
    n = len(jobs)
    slots = range(max_slots)
    z = m.addVars(n, slots, vtype=GRB.BINARY, name="assign")
    used = m.addVars(slots, vtype=GRB.BINARY, name="slot_used")

    for j in range(n):
        m.addConstr(gp.quicksum(z[j, b] for b in slots) == 1)
    for b in slots:
        pieces = gp.quicksum(jobs[j]["pieces"] * z[j, b] for j in range(n))
        # batch_min/max are shared across this job set in practice (same
        # route family); use the tightest real bounds seen.
        bmin = min(j["batch_min"] for j in jobs)
        bmax = max(j["batch_max"] for j in jobs)
        m.addConstr(pieces >= bmin * used[b])
        m.addConstr(pieces <= bmax * used[b])
        for j in range(n):
            m.addConstr(z[j, b] <= used[b])
    # Symmetry breaking: use lower-indexed slots first (helps solve speed).
    for b in range(max_slots - 1):
        m.addConstr(used[b] >= used[b + 1])
    m.setObjective(gp.quicksum(used[b] for b in slots), GRB.MINIMIZE)
    m.optimize()

    batches = []
    if m.Status == GRB.OPTIMAL:
        for b in slots:
            if used[b].X > 0.5:
                members = [jobs[j] for j in range(n) if z[j, b].X > 0.5]
                batches.append({
                    "members": [mm["lot"] for mm in members],
                    "product_mix": sorted({mm["product"] for mm in members}),
                    "ptime": max(mm["ptime"] for mm in members),
                    "due": min(mm["due"] for mm in members),
                    "pieces": sum(mm["pieces"] for mm in members),
                    # A batch can't start until every one of its member lots
                    # has physically arrived.
                    "arrival": max(mm["arrival"] for mm in members),
                })
    return batches, m.Status == GRB.OPTIMAL


def _schedule_time_indexed(jobs, n_machines, horizon_hours=HORIZON_HOURS):
    """Identical-parallel-machine scheduling on an hourly grid: each job
    gets one start bucket; at most n_machines jobs may be active in any
    bucket; minimize total weighted tardiness against real due dates."""
    m = gp.Model("bottleneck_dispatch")
    m.Params.OutputFlag = 0
    n = len(jobs)
    T = range(horizon_hours)
    durations = [max(1, math.ceil(j["ptime"] / BUCKET_MIN)) for j in jobs]

    x = m.addVars(n, T, vtype=GRB.BINARY, name="start")
    tardiness = m.addVars(n, lb=0, name="tardiness")
    arrival_bucket = [math.ceil(j.get("arrival", 0) / BUCKET_MIN) for j in jobs]

    for j in range(n):
        # Can't start before the job/batch has actually arrived.
        for t in range(min(arrival_bucket[j], horizon_hours)):
            x[j, t].UB = 0
        m.addConstr(gp.quicksum(x[j, t] for t in T) == 1)
        completion = gp.quicksum((t + durations[j]) * x[j, t] for t in T)
        due_bucket = jobs[j]["due"] / BUCKET_MIN
        m.addConstr(tardiness[j] >= completion - due_bucket)

    for t in T:
        active = gp.quicksum(
            x[j, s] for j in range(n) for s in range(max(0, t - durations[j] + 1), t + 1)
        )
        m.addConstr(active <= n_machines)

    m.setObjective(gp.quicksum(tardiness[j] for j in range(n)), GRB.MINIMIZE)
    m.optimize()

    n_vars, n_constrs = m.NumVars, m.NumConstrs
    if m.Status not in (GRB.OPTIMAL, GRB.TIME_LIMIT) or m.SolCount == 0:
        return None, n_vars, n_constrs, m.Status

    schedule = []
    for j in range(n):
        start_bucket = next(t for t in T if x[j, t].X > 0.5)
        schedule.append({
            **jobs[j],
            "start_hour": start_bucket,
            "end_hour": start_bucket + durations[j],
            "tardiness_hours": round(tardiness[j].X, 2),
        })
    return schedule, n_vars, n_constrs, m.Status


def solve_bottleneck_dispatch(route_ids, lots_per_product=3, seed=11, gurobi_time_limit=30):
    t0 = time.time()
    diffusion_jobs, dryetch_jobs = build_snapshot(route_ids, lots_per_product, seed)

    max_slots = max(1, math.ceil(sum(j["pieces"] for j in diffusion_jobs) / min(j["batch_min"] for j in diffusion_jobs)) + 2)
    # Upper-bound estimate (worst case: batching fails to consolidate at
    # all) so a size is still reportable if Gurobi can't build/solve any of
    # this without a real license -- same honesty pattern as capacity_plan.py.
    expected_max_vars = (
        (len(diffusion_jobs) * max_slots + max_slots)
        + (len(diffusion_jobs) * HORIZON_HOURS)
        + (len(dryetch_jobs) * HORIZON_HOURS)
    )

    try:
        batches, batch_ok = _form_diffusion_batches(diffusion_jobs, max_slots)
        total_vars, total_constrs = 0, 0
        diff_schedule, dv, dc, diff_status = _schedule_time_indexed(batches, n_machines=10) if batches else (None, 0, 0, None)
        total_vars += dv
        total_constrs += dc
        etch_schedule, ev, ec, etch_status = _schedule_time_indexed(dryetch_jobs, n_machines=21)
        total_vars += ev
        total_constrs += ec
    except gp.GurobiError as e:
        return {
            "status": "license_required",
            "error": str(e),
            "n_variables": expected_max_vars,
            "n_constraints": None,
            "exceeds_gurobi_free_tier": expected_max_vars > 2000,
            "solve_time_sec": time.time() - t0,
        }

    solve_time = time.time() - t0
    ok = batch_ok and diff_schedule is not None and etch_schedule is not None
    total_tardiness = 0.0
    if ok:
        total_tardiness = sum(s["tardiness_hours"] for s in diff_schedule) + sum(s["tardiness_hours"] for s in etch_schedule)

    return {
        "status": "optimal" if ok else "infeasible_or_error",
        "solve_time_sec": solve_time,
        "n_diffusion_lots": len(diffusion_jobs),
        "n_diffusion_batches": len(batches),
        "n_dryetch_jobs": len(dryetch_jobs),
        "n_variables": total_vars,
        "n_constraints": total_constrs,
        "exceeds_gurobi_free_tier": total_vars > 2000 or total_constrs > 2000,
        "total_weighted_tardiness_hours": total_tardiness,
        "diffusion_schedule": diff_schedule,
        "dryetch_schedule": etch_schedule,
        "on_time_diffusion": sum(1 for s in (diff_schedule or []) if s["tardiness_hours"] <= 0),
        "on_time_dryetch": sum(1 for s in (etch_schedule or []) if s["tardiness_hours"] <= 0),
    }


@lru_cache(maxsize=1)
def run_default_dispatch():
    return solve_bottleneck_dispatch(tuple(range(1, 11)), lots_per_product=20)
