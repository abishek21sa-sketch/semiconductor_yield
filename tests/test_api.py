"""
Integration tests against the actual FastAPI app -- these exercise the real
endpoints end-to-end (routing, serialization, error handling), not just the
pipeline functions directly. Background pipeline warm-up starts on lifespan
startup and shares the same lru_cache as these calls, so the first test to
touch a given scenario pays its real compute cost; later tests reuse it.
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health_is_immediate(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_status_shape(client):
    r = client.get("/api/status")
    assert r.status_code == 200
    body = r.json()
    assert "yield" in body and "scenarios" in body and "error" in body


def test_index_serves_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Fab Yield" in r.text


def test_client_side_route_falls_back_to_spa(client):
    """A direct hit on a React Router route (not a real file) must still serve
    the built index.html so refreshing /methodology in the browser works."""
    r = client.get("/methodology")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Fab Yield" in r.text


def test_static_assets_are_served(client):
    """The built JS bundle referenced by index.html must actually be reachable
    under /assets -- catches a StaticFiles mount pointed at the wrong dir."""
    index = client.get("/").text
    import re

    m = re.search(r'/assets/[^"]+\.js', index)
    assert m, "index.html did not reference a built JS bundle"
    r = client.get(m.group(0))
    assert r.status_code == 200
    assert "javascript" in r.headers["content-type"]


def test_list_scenarios_has_all_four(client):
    r = client.get("/api/scenarios")
    assert r.status_code == 200
    keys = {s["key"] for s in r.json()}
    assert keys == {"baseline", "photo_tool_down", "diffusion_pm", "demand_surge"}


def test_unknown_scenario_is_404(client):
    r = client.get("/api/scenario/does_not_exist")
    assert r.status_code == 404


def test_baseline_scenario_shape(client):
    r = client.get("/api/scenario/baseline")
    assert r.status_code == 200
    body = r.json()
    for key in ("capacity", "simulation", "optimization", "recommendation"):
        assert key in body
    assert body["capacity"]["bottleneck"] is not None
    assert len(body["recommendation"]) >= 1


def test_diffusion_outage_scenario_is_worse_than_baseline(client):
    baseline = client.get("/api/scenario/baseline").json()
    diffusion = client.get("/api/scenario/diffusion_pm").json()
    base_util = next(s["utilization"] for s in baseline["capacity"]["stations"] if s["stngrp"] == "Diffusion")
    cut_util = next(s["utilization"] for s in diffusion["capacity"]["stations"] if s["stngrp"] == "Diffusion")
    assert cut_util > base_util


def test_yield_endpoint_returns_real_secom_stats(client):
    r = client.get("/api/yield")
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["n_lots"] == 1567
    assert 0.0 < body["meta"]["yield_rate"] < 1.0
    assert 0.5 <= body["model"]["roc_auc"] <= 1.0
    assert len(body["top_sensors"]) > 0


def test_yield_theory_curve(client):
    r = client.get("/api/yield/theory?defect_density=0.5")
    assert r.status_code == 200
    curve = r.json()
    assert len(curve) == 40
    for row in curve:
        assert 0.0 <= row["poisson"] <= 1.0


def test_yield_theory_rejects_invalid_params(client):
    r = client.get("/api/yield/theory?defect_density=-1")
    assert r.status_code == 400
    r2 = client.get("/api/yield/theory?cluster_alpha=0")
    assert r2.status_code == 400


def test_capacity_plan_exceeds_free_tier(client):
    # "optimal" with a real Gurobi license (e.g. locally); "license_required"
    # without one (e.g. CI) -- Gurobi refusing to solve a >2000-variable
    # model unlicensed proves the same point as solving it does.
    r = client.get("/api/capacity_plan")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("optimal", "license_required")
    assert body["n_variables"] > 2000
    assert body["exceeds_gurobi_free_tier"] is True


def test_bottleneck_dispatch_shape(client):
    # Same two-outcome contract as test_capacity_plan_exceeds_free_tier: this
    # MILP's time-indexed formulation (96 hourly buckets x every job) exceeds
    # Gurobi's free tier even at the smallest snapshot size, so CI (unlicensed)
    # always sees "license_required" while a real license (e.g. locally)
    # sees "optimal" -- both prove the model is genuinely too big.
    r = client.get("/api/bottleneck_dispatch")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("optimal", "license_required")
    assert body["n_variables"] > 2000
    assert body["exceeds_gurobi_free_tier"] is True
    if body["status"] == "optimal":
        assert body["n_diffusion_lots"] > 0
        assert body["n_dryetch_jobs"] > 0


def test_wafer_defects_shape(client):
    # "trained" wherever scripts/train_wafer_cnn.py has been run (needs the
    # ~2GB WM-811K raw file, not in git); "not_trained" everywhere else
    # (e.g. CI, or a fresh clone) -- same graceful-degradation contract as
    # the license-gated MILPs.
    r = client.get("/api/wafer_defects")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("trained", "not_trained")
    if body["status"] == "trained":
        assert body["n_labeled_total"] == 172950
        assert len(body["classes"]) == 9
        assert 0 <= body["test_macro_f1"] <= 1


def test_topology_has_all_ten_real_products(client):
    r = client.get("/api/topology")
    assert r.status_code == 200
    body = r.json()
    assert len(body["route_ids"]) == 10
    assert "Diffusion" in body["stations"]
    assert body["stations"]["Diffusion"]["n_tools"] == 10
    assert all(v is not None for v in body["demand"].values())
