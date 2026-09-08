"""
Integration tests against the actual FastAPI app -- these exercise the real
endpoints end-to-end (routing, serialization, error handling), not just the
pipeline functions directly. Background pipeline warm-up starts on lifespan
startup and shares the same lru_cache as these calls, so the first test to
touch a given scenario pays its real compute cost; later tests reuse it.
"""
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.main import app  # noqa: E402
from api import db  # noqa: E402


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


def test_history_records_and_filters_by_run_type(client):
    """/api/history is supposed to read back real rows a prior request wrote
    (see api/db.py), filtered by run_type and ordered most-recent-first --
    none of that was previously exercised by any test. Uses a fresh,
    randomly-suffixed run_type per test invocation (rather than a fixed
    string) so this stays deterministic no matter how many times this test
    itself has already run against the real, persistent local fab_app.db --
    a fixed probe name would accumulate rows across repeated local runs."""
    probe_type = f"test_history_probe_{uuid.uuid4().hex}"
    db.record_run(probe_type, "run_a", "ok", {"x": 1})
    db.record_run(probe_type, "run_b", "ok", {"x": 2})

    r = client.get(f"/api/history?run_type={probe_type}")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 2
    assert all(row["run_type"] == probe_type for row in rows)
    # most-recent-first ordering (created_at desc)
    assert [row["run_key"] for row in rows] == ["run_b", "run_a"]
    assert rows[0]["summary"] == {"x": 2}
    assert rows[1]["summary"] == {"x": 1}

    # a run_type that was never recorded returns an empty list, not an error
    r_empty = client.get(f"/api/history?run_type=no_such_run_type_ever_{uuid.uuid4().hex}")
    assert r_empty.status_code == 200
    assert r_empty.json() == []


def test_history_limit_query_param_is_capped_at_200(client, monkeypatch):
    """SECURITY.md documents /api/history's limit as 'clamped server-side to
    200' -- this was asserted in prose but never actually checked by a test.
    Spies on api.db.get_history to confirm the route really does pass
    min(requested_limit, 200) through, not the raw client-supplied value."""
    captured = {}

    def fake_get_history(run_type=None, limit=50):
        captured["run_type"] = run_type
        captured["limit"] = limit
        return []

    monkeypatch.setattr(db, "get_history", fake_get_history)
    r = client.get("/api/history?limit=9999")
    assert r.status_code == 200
    assert captured["limit"] == 200

    # a limit already under the cap is passed through unchanged
    r2 = client.get("/api/history?limit=5")
    assert r2.status_code == 200
    assert captured["limit"] == 5


def test_spa_fallback_serves_correctly_as_the_very_first_request():
    """Every other test in this module reuses the module-scoped `client`
    fixture, which always hits '/' (test_index_serves_html) before any test
    reaches a client-side route -- so the SPA-fallback test never actually
    ran cold. This spins up a brand-new TestClient/app lifespan and makes
    '/methodology' the first and only request of that session, proving the
    fallback doesn't implicitly depend on '/' (or anything else) having
    already been served first, e.g. warming a cache of the built index.html."""
    with TestClient(app) as fresh_client:
        r = fresh_client.get("/methodology")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert "Fab Yield" in r.text
