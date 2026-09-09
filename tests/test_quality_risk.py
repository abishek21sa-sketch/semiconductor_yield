import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import quality_risk as qr


def test_none_class_is_excluded_from_risk_ranking():
    dist = {"none": 999999, "Center": 10}
    r = qr.quality_risk_by_station(dist)
    assert r["top_quality_risk_station"] == "Planar"
    assert sum(s["real_defect_count"] for s in r["stations"]) == 10


def test_shares_sum_to_one():
    dist = {"Center": 100, "Scratch": 50, "Loc": 25}
    r = qr.quality_risk_by_station(dist)
    total_share = sum(s["share_of_mapped_defects"] for s in r["stations"])
    assert abs(total_share - 1.0) < 1e-9


def test_empty_distribution_does_not_crash():
    r = qr.quality_risk_by_station({})
    assert r["top_quality_risk_station"] is None
    assert r["stations"] == []


def test_every_mapped_station_is_a_real_stngrp():
    """The mapping must only ever point at station groups that actually
    exist in the real SMT2020 topology, or downstream comparisons against
    the real capacity/bottleneck data would silently break."""
    import pipeline.fab_data as fd

    real_groups = set(fd.load_station_groups("lvhm").index)
    for grp in qr.DEFECT_TO_STATION_GROUP.values():
        assert grp in real_groups, f"{grp} is not a real SMT2020 station group"
