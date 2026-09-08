"""
Composes the capacity, simulation, and optimization layers into named
Quick Scenarios for the demo workspace, and generates an evidence-labeled
explainable recommendation from the combined results.
"""
from functools import lru_cache

from . import capacity, fab_twin, release_optimizer

ROUTE_IDS = list(range(1, 11))  # all 10 real products in the SMT2020 LVHM benchmark

SCENARIOS = {
    "baseline": {
        "label": "Baseline",
        "description": "Current real fab topology, tool counts, and reliability -- no changes.",
        "station_overrides": None,
        "release_interval_min": 800.0,
    },
    "photo_tool_down": {
        "label": "Litho tool-down (PM)",
        "description": "6 of the fab's real 11 litho tools taken down for preventive maintenance.",
        "station_overrides": {"Litho": {"n_tools": 5}},
        "release_interval_min": 800.0,
    },
    "diffusion_pm": {
        "label": "Diffusion furnace outage",
        "description": "3 of the fab's real 10 diffusion furnaces down -- the real bottleneck station takes the hit.",
        "station_overrides": {"Diffusion": {"n_tools": 7}},
        "release_interval_min": 800.0,
    },
    "demand_surge": {
        "label": "Demand surge",
        "description": "Order releases sped up ~35% (customers pulling in due dates) with no capacity change.",
        "station_overrides": None,
        "release_interval_min": 520.0,
    },
}

POLICIES = [
    {"name": "FIFO / uncontrolled release", "dispatch_rule": "fifo", "release_mode": "push"},
    {"name": "Critical Ratio / uncontrolled release", "dispatch_rule": "cr", "release_mode": "push"},
    {"name": "Critical Ratio / CONWIP", "dispatch_rule": "cr", "release_mode": "conwip", "conwip_cap": 15},
]


def _release_rate_per_min(release_interval_min):
    return 1.0 / (release_interval_min * len(ROUTE_IDS))


def _recommendation(scenario_key, cap_result, sim_result, opt_result, overridden_stations):
    lines = []
    bottleneck = cap_result["bottleneck"]
    bn = next((s for s in cap_result["stations"] if s["stngrp"] == bottleneck), None)
    if bn:
        lines.append(
            f"[real topology + queueing theory] {bottleneck} is the emerging bottleneck at "
            f"{bn['utilization']:.0%} utilization (Kingman-approx queue wait "
            f"{bn['kingman_wait_min']:.0f} min)."
        )
    if overridden_stations and bottleneck not in overridden_stations:
        lines.append(
            f"[capacity analysis] This scenario changes {', '.join(overridden_stations)} capacity, but "
            f"{bottleneck} remains the binding constraint -- so weekly output is unaffected. That's a real "
            f"finding: {', '.join(overridden_stations)} has slack to absorb downtime without hurting throughput."
        )

    best_policy = min(
        (p for p in sim_result if p["mean_cycle_time_min"] is not None),
        key=lambda p: p["mean_cycle_time_min"],
        default=None,
    )
    worst_policy = max(
        (p for p in sim_result if p["mean_cycle_time_min"] is not None),
        key=lambda p: p["mean_cycle_time_min"],
        default=None,
    )
    if best_policy and worst_policy and best_policy is not worst_policy:
        delta = worst_policy["mean_cycle_time_min"] - best_policy["mean_cycle_time_min"]
        pct = delta / worst_policy["mean_cycle_time_min"] if worst_policy["mean_cycle_time_min"] else 0
        lines.append(
            f"[simulated, Monte Carlo over the real topology] '{best_policy['policy']}' beats "
            f"'{worst_policy['policy']}' by {pct:.0%} mean cycle time "
            f"({best_policy['mean_cycle_time_min']:.0f} vs {worst_policy['mean_cycle_time_min']:.0f} min)."
        )

    if opt_result["status"] == "optimal":
        total = sum(opt_result["release_plan"].values())
        lines.append(
            f"[Gurobi-optimized against real order demand] Recommended weekly release: "
            f"{opt_result['release_plan']} ({total} lots/week total), binding constraint: "
            f"{opt_result['binding_station']}."
        )
    else:
        lines.append(
            f"[Gurobi] This scenario makes the minimum committed fill rate infeasible -- "
            f"no release plan can satisfy all {len(ROUTE_IDS)} products' service floor under this capacity."
        )

    return lines


@lru_cache(maxsize=None)
def run_scenario(name: str):
    if name not in SCENARIOS:
        raise KeyError(f"unknown scenario '{name}'")
    cfg = SCENARIOS[name]
    overrides = cfg["station_overrides"]
    release_interval = cfg["release_interval_min"]

    cap_result = capacity.station_utilization(
        ROUTE_IDS, _release_rate_per_min(release_interval), station_overrides=overrides,
    )
    sim_result = fab_twin.monte_carlo_policy_comparison(
        ROUTE_IDS, release_interval, POLICIES, n_replications=3, sim_days=30, station_overrides=overrides,
    )
    min_fill = 0.048 if name == "demand_surge" else 0.02
    opt_result = release_optimizer.optimize_release_mix(
        ROUTE_IDS, station_overrides=overrides, min_fill_rate=min_fill,
    )

    return {
        "scenario": name,
        "label": cfg["label"],
        "description": cfg["description"],
        "capacity": cap_result,
        "simulation": sim_result,
        "optimization": opt_result,
        "recommendation": _recommendation(
            name, cap_result, sim_result, opt_result,
            overridden_stations=list(overrides.keys()) if overrides else [],
        ),
    }


def list_scenarios():
    return [{"key": k, "label": v["label"], "description": v["description"]} for k, v in SCENARIOS.items()]
