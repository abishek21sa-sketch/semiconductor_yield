"""
Deterministic industrial-engineering math: Little's Law, the Kingman G/G/1
(and G/G/m) waiting-time approximation, and station-group bottleneck /
utilization analysis built on the real SMT2020 topology in fab_data.py.

These are closed-form textbook results (Little 1961; Kingman 1961's VUT
equation) -- they are exact/approximate by construction, not fit to data,
which is why they're covered by unit tests rather than cross-validation.
"""
import math

from . import fab_data


def littles_law_cycle_time(wip: float, throughput_per_min: float) -> float:
    """L = lambda * W  =>  W = L / lambda. Returns cycle time in minutes."""
    if throughput_per_min <= 0:
        return math.inf
    return wip / throughput_per_min


def littles_law_wip(throughput_per_min: float, cycle_time_min: float) -> float:
    return throughput_per_min * cycle_time_min


def kingman_wait_time(ca2: float, cs2: float, m: int, mean_service_min: float, utilization: float) -> float:
    """Kingman's VUT (G/G/m) approximation for expected queueing wait time.

    Wq ~= ( (ca^2 + cs^2) / 2 ) * ( u^(sqrt(2*(m+1)) - 1) / (1 - u) ) * (service_time / m)

    ca2/cs2: squared coefficients of variation of interarrival/service times.
    m: number of parallel machines in the station group.
    utilization: rho, in (0, 1).
    """
    if utilization >= 1.0:
        return math.inf
    if utilization <= 0:
        return 0.0
    variability_term = (ca2 + cs2) / 2
    exponent = math.sqrt(2 * (m + 1)) - 1
    utilization_term = (utilization ** exponent) / (1 - utilization)
    return variability_term * utilization_term * (mean_service_min / max(m, 1))


def station_utilization(route_ids, release_rate_per_min, ca2=1.0, cs2=0.25, station_overrides=None):
    """For each station group touched by the given routes (equal release
    rate per route, in lots/min), compute real-topology-derived load,
    utilization, and Kingman queueing time -- flags the bottleneck.

    cs2 default of 0.25 reflects the benchmark's own processing-time spread
    (PTIME2 ~= 5% of PTIME => a tight, near-deterministic service process,
    consistent with automated fab tools); ca2=1.0 assumes Poisson-ish lot
    releases (a conservative default; CONWIP release tightens this)."""
    stations = fab_data.apply_station_overrides(fab_data.load_station_groups(), station_overrides)
    load_min_per_min = {g: 0.0 for g in stations.index}

    for rid in route_ids:
        steps = fab_data.load_route(rid)
        by_group = steps.groupby("stngrp")["mean_ptime_min"].sum()
        for g, total_min in by_group.items():
            if g in load_min_per_min:
                load_min_per_min[g] += total_min * release_rate_per_min

    results = []
    for g, load in load_min_per_min.items():
        row = stations.loc[g]
        m = max(int(row["n_tools"]), 1)
        availability = float(row["availability"])
        effective_capacity_per_min = m * availability  # in "machine-minutes of work per minute"
        if g.startswith("Delay"):
            continue  # transport/queue placeholder, not a physical capacity constraint
        utilization = load / effective_capacity_per_min if effective_capacity_per_min > 0 else math.inf
        mean_service = load / (release_rate_per_min * len(route_ids)) if release_rate_per_min > 0 else 0.0
        wq = kingman_wait_time(ca2, cs2, m, mean_service, min(utilization, 0.999)) if utilization < 1 else math.inf
        results.append({
            "stngrp": g,
            "n_tools": m,
            "availability": availability,
            "load_min_per_min": load,
            "effective_capacity_per_min": effective_capacity_per_min,
            "utilization": utilization,
            "kingman_wait_min": wq,
        })
    results.sort(key=lambda r: r["utilization"], reverse=True)
    bottleneck = results[0]["stngrp"] if results else None
    return {"stations": results, "bottleneck": bottleneck}
