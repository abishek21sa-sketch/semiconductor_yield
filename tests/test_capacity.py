import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import capacity, fab_data


def test_littles_law_round_trip():
    wip = 12.0
    throughput = 0.02  # lots/min
    ct = capacity.littles_law_cycle_time(wip, throughput)
    assert math.isclose(capacity.littles_law_wip(throughput, ct), wip, rel_tol=1e-9)


def test_littles_law_zero_throughput_is_infinite_cycle_time():
    assert capacity.littles_law_cycle_time(10.0, 0.0) == math.inf


def test_kingman_matches_exact_mm1_formula():
    # For an M/M/1 queue (ca2 = cs2 = 1, m = 1), Kingman's VUT approximation
    # is exact: Wq = (rho / (1 - rho)) * service_time.
    service_time, rho = 5.0, 0.7
    expected = (rho / (1 - rho)) * service_time
    got = capacity.kingman_wait_time(ca2=1.0, cs2=1.0, m=1, mean_service_min=service_time, utilization=rho)
    assert math.isclose(got, expected, rel_tol=1e-9)


def test_kingman_wait_grows_with_utilization():
    waits = [
        capacity.kingman_wait_time(ca2=1.0, cs2=0.25, m=4, mean_service_min=10.0, utilization=u)
        for u in (0.2, 0.5, 0.8, 0.95)
    ]
    assert waits == sorted(waits)


def test_kingman_at_or_above_capacity_is_infinite_or_undefined():
    assert capacity.kingman_wait_time(1.0, 1.0, 1, 10.0, utilization=1.0) == math.inf
    assert capacity.kingman_wait_time(1.0, 1.0, 1, 10.0, utilization=0.0) == 0.0


def test_station_groups_have_sane_real_values():
    stations = fab_data.load_station_groups()
    assert len(stations) > 0
    for grp, row in stations.iterrows():
        assert row["n_tools"] >= 1
        assert 0.0 < row["availability"] <= 1.0


def test_station_utilization_identifies_a_bottleneck():
    result = capacity.station_utilization([1, 2, 3], release_rate_per_min=0.0007)
    assert result["bottleneck"] is not None
    utils = [s["utilization"] for s in result["stations"]]
    assert utils == sorted(utils, reverse=True)


def test_station_overrides_reduce_capacity():
    baseline = capacity.station_utilization([1, 2, 3], release_rate_per_min=0.0006)
    cut = capacity.station_utilization(
        [1, 2, 3], release_rate_per_min=0.0006, station_overrides={"Diffusion": {"n_tools": 3}},
    )
    base_diff = next(s for s in baseline["stations"] if s["stngrp"] == "Diffusion")
    cut_diff = next(s for s in cut["stations"] if s["stngrp"] == "Diffusion")
    assert cut_diff["utilization"] > base_diff["utilization"]
