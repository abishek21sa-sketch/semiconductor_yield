"""
Gurobi MILP: capacity-constrained lot-release mix optimization (a real
rough-cut-capacity-planning problem), built on the real SMT2020 station-
group tool counts/availability and route processing times.

Decision: how many lots of each product to release this planning period to
maximize weighted throughput without exceeding any station group's real
capacity -- optionally under a scenario that changes a station's tool count
(e.g. "2 of 11 litho tools down for PM").
"""
import gurobipy as gp
from gurobipy import GRB

from . import fab_data


def optimize_release_mix(
    route_ids, period_minutes=60 * 24 * 7, weights=None,
    demand_ceiling=None, min_fill_rate=0.02, station_overrides=None,
):
    """min_fill_rate: minimum fraction of each product's real weekly demand
    (from order.txt) that must be released -- models a minimum contractual
    fill-rate commitment per product line, so the optimizer must serve all
    products instead of dumping every lot into whichever is cheapest on the
    bottleneck. Real demand is far above what the real bottleneck can supply
    in this benchmark, so demand itself isn't a binding ceiling -- it's the
    ordering priority the optimizer allocates scarce capacity against."""
    stations = fab_data.apply_station_overrides(fab_data.load_station_groups(), station_overrides)

    demand = fab_data.load_demand()
    real_weekly_demand = {
        rid: float(demand.loc[rid, "weekly_demand_lots"]) if rid in demand.index else 10.0
        for rid in route_ids
    }
    scale = period_minutes / (60 * 24 * 7)
    demand_ceiling = demand_ceiling or {rid: real_weekly_demand[rid] * scale for rid in route_ids}
    min_release = {rid: min_fill_rate * real_weekly_demand[rid] * scale for rid in route_ids}
    weights = weights or {rid: 1.0 for rid in route_ids}

    route_step_totals = {}
    for rid in route_ids:
        steps = fab_data.load_route(rid)
        route_step_totals[rid] = steps.groupby("stngrp")["mean_ptime_min"].sum().to_dict()

    m = gp.Model("fab_release_mix")
    m.Params.OutputFlag = 0
    x = {
        rid: m.addVar(
            vtype=GRB.INTEGER, lb=min_release.get(rid, 0), ub=max(demand_ceiling.get(rid, 50), 1),
            name=f"release_{rid}",
        )
        for rid in route_ids
    }

    for grp, row in stations.iterrows():
        if grp.startswith("Delay"):
            continue
        capacity_min = row["n_tools"] * row["availability"] * period_minutes
        load = gp.quicksum(x[rid] * route_step_totals[rid].get(grp, 0.0) for rid in route_ids)
        m.addConstr(load <= capacity_min, name=f"cap_{grp}")

    m.setObjective(gp.quicksum(weights.get(rid, 1.0) * x[rid] for rid in route_ids), GRB.MAXIMIZE)
    m.optimize()

    if m.Status != GRB.OPTIMAL:
        return {"status": "infeasible_or_error", "gurobi_status": m.Status}

    release_plan = {rid: int(round(x[rid].X)) for rid in route_ids}

    binding = []
    for grp, row in stations.iterrows():
        if grp.startswith("Delay"):
            continue
        capacity_min = row["n_tools"] * row["availability"] * period_minutes
        load = sum(release_plan[rid] * route_step_totals[rid].get(grp, 0.0) for rid in route_ids)
        binding.append({
            "stngrp": grp,
            "n_tools": float(row["n_tools"]),
            "utilization": (load / capacity_min) if capacity_min else None,
            "load_min": load,
            "capacity_min": capacity_min,
        })
    binding.sort(key=lambda r: r["utilization"] or 0, reverse=True)

    demand_report = {
        rid: {
            "weekly_demand_lots_real": real_weekly_demand[rid],
            "released": release_plan[rid],
            "fill_rate": release_plan[rid] / demand_ceiling[rid] if demand_ceiling[rid] else None,
        }
        for rid in route_ids
    }

    return {
        "status": "optimal",
        "objective": m.ObjVal,
        "release_plan": release_plan,
        "demand": demand_report,
        "period_minutes": period_minutes,
        "station_utilization": binding,
        "binding_station": binding[0]["stngrp"] if binding else None,
    }
