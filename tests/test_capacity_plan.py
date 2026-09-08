import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import capacity_plan

ROUTE_IDS = list(range(1, 11))


def test_plan_exceeds_gurobi_free_tier():
    """The whole point of this module: prove the problem is genuinely too
    big for Gurobi's bundled size-limited free tier (2000 vars/constraints),
    unlike the single-week release_optimizer MILP. With a real license
    (e.g. locally) it solves and returns "optimal"; without one (e.g. CI)
    Gurobi refuses outright and we get "license_required" -- both outcomes
    prove the same point, so both are accepted here."""
    r = capacity_plan.solve_multi_period_plan(ROUTE_IDS, weeks=26, n_scenarios=10)
    assert r["status"] in ("optimal", "license_required")
    assert r["n_variables"] > 2000
    assert r["n_constraints"] > 2000
    assert r["exceeds_gurobi_free_tier"] is True


def test_backlog_accounting_is_consistent():
    r = capacity_plan.solve_multi_period_plan(ROUTE_IDS, weeks=12, n_scenarios=5)
    assert r["status"] == "optimal"
    demand = capacity_plan.fab_data.load_demand()
    for rid in ROUTE_IDS:
        weekly_demand = float(demand.loc[rid, "weekly_demand_lots"])
        releases = r["release_plan"][rid]
        backlog = r["backlog_trajectory"][rid]
        running = 0.0
        for w, (rel, bl) in enumerate(zip(releases, backlog)):
            running += weekly_demand - rel
            assert abs(running - bl) < 0.5, f"product {rid} week {w}: expected backlog {running}, got {bl}"


def test_cumulative_floor_is_respected():
    min_fill_rate = 0.02
    weeks = 12
    r = capacity_plan.solve_multi_period_plan(ROUTE_IDS, weeks=weeks, n_scenarios=5, min_fill_rate=min_fill_rate)
    assert r["status"] == "optimal"
    demand = capacity_plan.fab_data.load_demand()
    for rid in ROUTE_IDS:
        weekly_demand = float(demand.loc[rid, "weekly_demand_lots"])
        total_released = sum(r["release_plan"][rid])
        assert total_released >= min_fill_rate * weekly_demand * weeks - 1e-6


def test_smaller_horizon_solves_fast():
    r = capacity_plan.solve_multi_period_plan(ROUTE_IDS, weeks=12, n_scenarios=5)
    assert r["status"] == "optimal"
    assert r["solve_time_sec"] < 30
