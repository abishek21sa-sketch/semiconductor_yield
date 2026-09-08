"""
Two-stage stochastic multi-period capacity & release plan -- a Gurobi MILP
large enough to genuinely need a real license, not the ~10-variable
single-week release mix in release_optimizer.py (which fits inside Gurobi's
bundled size-limited free tier and doesn't prove anything about having a
real license).

First stage (here-and-now, decided before uncertainty resolves): how many
lots of each of the 10 real products to release each week over a real
planning horizon.

Uncertainty: each station group's real weekly capacity, sampled via Monte
Carlo from the benchmark's own real exponential MTBF/MTTR parameters
(downcal.txt) -- a standard sample-average-approximation (SAA) treatment of
a compound-Poisson renewal process (number of failures in a week ~ Poisson,
each failure's downtime ~ Exp(MTTR), so total downtime ~ Gamma(N, MTTR)).

Second stage (recourse, one set of variables per scenario): if a scenario's
realized capacity falls short of what the first-stage release plan
committed to, that shortfall is covered at a penalty cost (representing
real overtime/expediting) rather than being infeasible -- the standard way
to model "the plan is made now, reality resolves later" in stochastic
programming. Real overtime can only buy a bounded amount of extra capacity,
so shortfall is capped, not unlimited.

This deliberately produces thousands of variables (10 products x T weeks
+ 12 stations x T weeks x K scenarios), well past Gurobi's free 2000-var/
2000-constraint limit -- reported explicitly in the result so it's
provable, not just claimed. Without a real license, Gurobi refuses to
build/solve a model this size at all (see the try/except below) -- that
refusal is surfaced as status "license_required" rather than crashing.
"""
import time
from functools import lru_cache

import numpy as np
import gurobipy as gp
from gurobipy import GRB

from . import fab_data

WEEK_MIN = 60 * 24 * 7


def _sample_weekly_capacity(stations, weeks, n_scenarios, seed=7):
    """SAA scenario generation: for every (station, tool, week, scenario),
    draw the number of real breakdown events ~ Poisson(week_min/MTBF), then
    total downtime ~ Gamma(N, scale=MTTR) (sum of N iid Exp(MTTR) draws,
    exact for N>0, 0 for N=0). Returns capacity_min[station][week][scenario]
    in available machine-minutes, summed across that station's real tool
    count. This is a fixed-window approximation of a renewal process (it
    doesn't carry a failure that starts near a week boundary into the next
    week) -- a stated simplification, not hidden."""
    rng = np.random.default_rng(seed)
    capacity = {}
    for grp, row in stations.iterrows():
        if grp.startswith("Delay"):
            continue
        n_tools = int(row["n_tools"])
        mtbf, mttr = float(row["MTTF"]), float(row["MTTR"])
        lam = WEEK_MIN / mtbf if mtbf > 0 else 0.0
        n_events = rng.poisson(lam, size=(weeks, n_scenarios, n_tools))
        downtime = np.where(
            n_events > 0,
            rng.gamma(shape=np.maximum(n_events, 1), scale=mttr),
            0.0,
        )
        downtime = np.minimum(downtime, WEEK_MIN)
        available_per_tool = WEEK_MIN - downtime
        capacity[grp] = available_per_tool.sum(axis=2)  # (weeks, scenarios) machine-minutes
    return capacity


def _build_and_solve(
    route_ids, weeks, n_scenarios, station_groups, capacity_scen,
    weekly_demand, route_step_totals, min_fill_rate, overtime_cap_fraction,
    shortfall_penalty, backlog_penalty, priority_weights,
):
    """Builds and solves the full MILP. Raises gp.GurobiError (uncaught) if
    Gurobi can't build or solve a model this size without a real license --
    the caller decides what to do with that."""
    W, K = range(weeks), range(n_scenarios)

    m = gp.Model("multi_period_capacity_plan")
    m.Params.OutputFlag = 0

    release = m.addVars(route_ids, W, vtype=GRB.INTEGER, lb=0, ub=100, name="release")
    backlog = m.addVars(route_ids, W, vtype=GRB.CONTINUOUS, lb=0, name="backlog")
    shortfall = m.addVars(station_groups, W, K, vtype=GRB.CONTINUOUS, lb=0, name="shortfall")

    # A minimum-fill-rate floor (same modeling choice as release_optimizer.py)
    # keeps the plan from degenerately dumping every lot into whichever
    # product is cheapest on the bottleneck and starving the other 9. It's
    # cumulative over the horizon, not per-week: real minimum commitments
    # are typically met on average over a planning period, and a hard
    # per-week floor combined with the overtime cap below can make some
    # weeks infeasible outright when that week's sampled capacity is
    # unusually bad.
    for rid in route_ids:
        m.addConstr(
            gp.quicksum(release[rid, w] for w in W) >= min_fill_rate * weekly_demand[rid] * weeks,
            name=f"min_release_cumulative_{rid}",
        )

    for rid in route_ids:
        m.addConstr(backlog[rid, 0] == weekly_demand[rid] - release[rid, 0])
        for w in range(1, weeks):
            m.addConstr(backlog[rid, w] == backlog[rid, w - 1] + weekly_demand[rid] - release[rid, w])

    for grp in station_groups:
        for w in W:
            load = gp.quicksum(release[rid, w] * route_step_totals[rid].get(grp, 0.0) for rid in route_ids)
            for k in K:
                cap = float(capacity_scen[grp][w, k])
                m.addConstr(load - shortfall[grp, w, k] <= cap, name=f"cap_{grp}_{w}_{k}")
                # Real overtime/expediting can buy some extra capacity, not
                # unlimited amounts -- without this cap a cheap-enough
                # shortfall penalty lets the model "pay" its way to
                # unbounded capacity, which real fabs cannot do.
                m.addConstr(shortfall[grp, w, k] <= overtime_cap_fraction * cap, name=f"overtime_cap_{grp}_{w}_{k}")

    # Shortfall is naturally in machine-minutes (it lives in the capacity
    # constraint), while backlog is in lots -- comparing them directly in the
    # objective would let a few hundred minutes of overrun swamp a lot of
    # actual backlog. Normalize each station's shortfall to lot-equivalents
    # by its own average real per-lot load, so both cost terms are in the
    # same "lots" currency and the penalty weights are directly comparable.
    avg_load = {
        grp: (sum(route_step_totals[rid].get(grp, 0.0) for rid in route_ids) / len(route_ids)) or 1.0
        for grp in station_groups
    }
    backlog_cost = gp.quicksum(priority_weights[rid] * backlog_penalty * backlog[rid, w] for rid in route_ids for w in W)
    shortfall_cost = gp.quicksum(
        shortfall_penalty * (shortfall[grp, w, k] / avg_load[grp])
        for grp in station_groups for w in W for k in K
    ) / n_scenarios
    m.setObjective(backlog_cost + shortfall_cost, GRB.MINIMIZE)

    m.optimize()
    return m, release, backlog, shortfall


def solve_multi_period_plan(
    route_ids, weeks=26, n_scenarios=10, shortfall_penalty=8.0,
    backlog_penalty=1.0, min_fill_rate=0.02, overtime_cap_fraction=0.20,
    seed=7, priority_weights=None,
):
    t0 = time.time()
    stations = fab_data.load_station_groups()
    demand = fab_data.load_demand()
    weekly_demand = {
        rid: float(demand.loc[rid, "weekly_demand_lots"]) if rid in demand.index else 10.0
        for rid in route_ids
    }
    priority_weights = priority_weights or {rid: 1.0 for rid in route_ids}

    route_step_totals = {}
    for rid in route_ids:
        steps = fab_data.load_route(rid)
        route_step_totals[rid] = steps.groupby("stngrp")["mean_ptime_min"].sum().to_dict()

    station_groups = [g for g in stations.index if not g.startswith("Delay")]
    capacity_scen = _sample_weekly_capacity(stations, weeks, n_scenarios, seed=seed)

    n_products, n_stations = len(route_ids), len(station_groups)
    # Computed analytically (not read off the Gurobi model) so the true size
    # is known and reportable even if Gurobi never manages to build/solve
    # the model at all -- e.g. no license, and the free tier refuses before
    # optimize() is ever reached.
    expected_n_vars = n_products * weeks * 2 + n_stations * weeks * n_scenarios
    expected_n_constrs = n_products * weeks + n_products + n_stations * weeks * n_scenarios * 2

    try:
        m, release, backlog, shortfall = _build_and_solve(
            route_ids, weeks, n_scenarios, station_groups, capacity_scen,
            weekly_demand, route_step_totals, min_fill_rate, overtime_cap_fraction,
            shortfall_penalty, backlog_penalty, priority_weights,
        )
    except gp.GurobiError as e:
        return {
            "status": "license_required",
            "error": str(e),
            "n_variables": expected_n_vars,
            "n_constraints": expected_n_constrs,
            "exceeds_gurobi_free_tier": expected_n_vars > 2000 or expected_n_constrs > 2000,
            "solve_time_sec": time.time() - t0,
        }

    solve_time = time.time() - t0
    n_vars, n_constrs = m.NumVars, m.NumConstrs
    W, K = range(weeks), range(n_scenarios)

    if m.Status != GRB.OPTIMAL:
        return {
            "status": "infeasible_or_error", "gurobi_status": m.Status,
            "n_variables": n_vars, "n_constraints": n_constrs,
        }

    release_plan = {rid: [round(release[rid, w].X) for w in W] for rid in route_ids}
    backlog_trajectory = {rid: [round(backlog[rid, w].X, 1) for w in W] for rid in route_ids}
    expected_shortfall_by_station = {
        grp: float(sum(shortfall[grp, w, k].X for w in W for k in K) / n_scenarios)
        for grp in station_groups
    }

    return {
        "status": "optimal",
        "objective": m.ObjVal,
        "solve_time_sec": solve_time,
        "n_variables": n_vars,
        "n_constraints": n_constrs,
        "exceeds_gurobi_free_tier": n_vars > 2000 or n_constrs > 2000,
        "weeks": weeks,
        "n_scenarios": n_scenarios,
        "release_plan": release_plan,
        "backlog_trajectory": backlog_trajectory,
        "total_backlog_final_week": sum(backlog_trajectory[rid][-1] for rid in route_ids),
        "expected_shortfall_by_station": expected_shortfall_by_station,
        "worst_shortfall_station": max(expected_shortfall_by_station, key=expected_shortfall_by_station.get),
    }


@lru_cache(maxsize=1)
def run_default_plan():
    """Cached entry point for the API/frontend: the 10-product, 26-week,
    10-scenario plan at tuned default parameters."""
    return solve_multi_period_plan(tuple(range(1, 11)))
