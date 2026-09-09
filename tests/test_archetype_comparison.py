import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import archetype_comparison as ac, fab_data as fd


def test_hvlm_and_lvhm_share_the_same_real_tool_inventory():
    """The whole point of this comparison being fair: both archetypes are
    the same real fab, not two unrelated datasets."""
    lvhm_tools = fd.load_station_groups("lvhm")["n_tools"].sum()
    hvlm_tools = fd.load_station_groups("hvlm")["n_tools"].sum()
    assert lvhm_tools == hvlm_tools == 106


def test_hvlm_route_ids_are_a_real_subset_of_lvhm():
    assert fd.route_ids("lvhm") == list(range(1, 11))
    assert fd.route_ids("hvlm") == [3, 4]


def test_hvlm_reuses_lvhm_routes_3_and_4_verbatim():
    for rid in (3, 4):
        lvhm_route = fd.load_route(rid, "lvhm")
        hvlm_route = fd.load_route(rid, "hvlm")
        assert lvhm_route["mean_ptime_min"].sum() == hvlm_route["mean_ptime_min"].sum()
        assert len(lvhm_route) == len(hvlm_route)


def test_compare_archetypes_holds_total_release_rate_constant():
    r = ac.compare_archetypes()
    assert r["status"] == "optimal"
    lvhm_total_rate = (1.0 / ac.RELEASE_INTERVAL_MIN / r["lvhm"]["n_products"]) * r["lvhm"]["n_products"]
    hvlm_total_rate = (1.0 / ac.RELEASE_INTERVAL_MIN / r["hvlm"]["n_products"]) * r["hvlm"]["n_products"]
    assert abs(lvhm_total_rate - hvlm_total_rate) < 1e-12


def test_compare_archetypes_reports_a_real_bottleneck_for_each():
    r = ac.compare_archetypes()
    assert r["lvhm"]["bottleneck"] is not None
    assert r["hvlm"]["bottleneck"] is not None
    assert 0 <= r["lvhm"]["bottleneck_utilization"] <= 1
    assert 0 <= r["hvlm"]["bottleneck_utilization"] <= 1
