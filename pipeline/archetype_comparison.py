"""
Real comparison between the SMT2020 benchmark's two published fab
archetypes: LVHM (Low-Volume-High-Mix, 10 real products, used everywhere
else in this app) and HVLM (High-Volume-Low-Mix, 2 real products) -- see
data/smt2020_hvlm/ATTRIBUTION.md.

Both archetypes share the SAME real tool inventory (106 tools total) and
even reuse the same two real route files (route_3.txt, route_4.txt are
byte-identical between the two archetype folders) -- the real difference is
how real demand concentrates. LVHM's real order.txt spreads ~390 lots/week
across 10 products; HVLM's real order.txt concentrates the same ~390
lots/week onto just 2. That's the actual research question: same fab, same
tools, same total demand -- does concentrating it onto fewer products change
where the bottleneck is or how bad it gets?

To make that a fair comparison rather than an artifact of picking two
different release paces, both are evaluated at the SAME total system
release rate (matching this app's existing "baseline" scenario in
scenarios.py) -- only how many products share that rate differs, exactly
mirroring the real demand-concentration difference between the two
archetypes' own order.txt files.
"""
from functools import lru_cache

from . import capacity, fab_data

RELEASE_INTERVAL_MIN = 800.0  # matches scenarios.py SCENARIOS["baseline"]["release_interval_min"]


def _archetype_snapshot(archetype: str, total_system_rate: float) -> dict:
    route_ids = fab_data.route_ids(archetype)
    per_route_rate = total_system_rate / len(route_ids)
    cap_result = capacity.station_utilization(route_ids, per_route_rate, archetype=archetype)
    demand = fab_data.load_demand(archetype)
    bottleneck = next(s for s in cap_result["stations"] if s["stngrp"] == cap_result["bottleneck"])
    return {
        "archetype": archetype,
        "n_products": len(route_ids),
        "route_ids": route_ids,
        "total_real_weekly_demand_lots": float(demand["weekly_demand_lots"].sum()),
        "bottleneck": cap_result["bottleneck"],
        "bottleneck_utilization": bottleneck["utilization"],
        "bottleneck_wait_min": bottleneck["kingman_wait_min"],
        "stations": cap_result["stations"],
    }


@lru_cache(maxsize=1)
def compare_archetypes() -> dict:
    """The real headline comparison: same tools, same total release rate,
    different product-mix concentration -- computed fresh from both
    archetypes' real topology/route/demand files, nothing precomputed or
    asserted in advance."""
    total_system_rate = 1.0 / RELEASE_INTERVAL_MIN
    lvhm = _archetype_snapshot("lvhm", total_system_rate)
    hvlm = _archetype_snapshot("hvlm", total_system_rate)

    same_tools = fab_data.load_station_groups("lvhm")["n_tools"].sum() == fab_data.load_station_groups("hvlm")["n_tools"].sum()
    same_bottleneck_station = lvhm["bottleneck"] == hvlm["bottleneck"]
    util_delta = hvlm["bottleneck_utilization"] - lvhm["bottleneck_utilization"]
    wait_delta_pct = (hvlm["bottleneck_wait_min"] / lvhm["bottleneck_wait_min"] - 1.0) if lvhm["bottleneck_wait_min"] > 0 else None

    return {
        "status": "optimal",
        "release_interval_min": RELEASE_INTERVAL_MIN,
        "lvhm": lvhm,
        "hvlm": hvlm,
        "same_physical_tool_count": bool(same_tools),
        "same_bottleneck_station": same_bottleneck_station,
        "bottleneck_utilization_delta": util_delta,
        "bottleneck_wait_delta_fraction": wait_delta_pct,
    }
