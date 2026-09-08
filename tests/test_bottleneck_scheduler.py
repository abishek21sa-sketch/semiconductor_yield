import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import bottleneck_scheduler as bs

ROUTE_IDS = list(range(1, 11))


def _max_concurrent(schedule, horizon):
    return max(
        sum(1 for s in schedule if s["start_hour"] <= h < s["end_hour"])
        for h in range(horizon)
    )


def test_no_capacity_violation_under_load():
    r = bs.solve_bottleneck_dispatch(ROUTE_IDS, lots_per_product=20)
    assert r["status"] == "optimal"
    assert _max_concurrent(r["diffusion_schedule"], bs.HORIZON_HOURS) <= 10
    assert _max_concurrent(r["dryetch_schedule"], bs.HORIZON_HOURS) <= 21


def test_jobs_never_start_before_arrival():
    r = bs.solve_bottleneck_dispatch(ROUTE_IDS, lots_per_product=10)
    assert r["status"] == "optimal"
    for s in r["dryetch_schedule"]:
        assert s["start_hour"] * bs.BUCKET_MIN >= s["arrival"] - bs.BUCKET_MIN  # within one bucket's rounding
    for s in r["diffusion_schedule"]:
        assert s["start_hour"] * bs.BUCKET_MIN >= s["arrival"] - bs.BUCKET_MIN


def test_batch_formation_respects_real_pieces_bounds():
    diffusion_jobs, _ = bs.build_snapshot(ROUTE_IDS, lots_per_product=10)
    batches, ok = bs._form_diffusion_batches(diffusion_jobs, max_slots=10)
    assert ok
    bmin = min(j["batch_min"] for j in diffusion_jobs)
    bmax = max(j["batch_max"] for j in diffusion_jobs)
    for b in batches:
        assert bmin <= b["pieces"] <= bmax
    # every lot assigned exactly once across all batches
    all_members = [lot for b in batches for lot in b["members"]]
    assert sorted(all_members) == sorted(j["lot"] for j in diffusion_jobs)


def test_tardiness_emerges_under_realistic_load():
    """Sanity check that the objective isn't trivially always zero -- if
    dry-etch demand exceeds its real 21-tool capacity within the dispatch
    horizon, some jobs should be genuinely late."""
    r = bs.solve_bottleneck_dispatch(ROUTE_IDS, lots_per_product=20)
    assert r["status"] == "optimal"
    assert r["total_weighted_tardiness_hours"] > 0
    assert r["on_time_dryetch"] < r["n_dryetch_jobs"]


def test_small_snapshot_solves_fast():
    r = bs.solve_bottleneck_dispatch(ROUTE_IDS, lots_per_product=3)
    assert r["status"] == "optimal"
    assert r["solve_time_sec"] < 15
