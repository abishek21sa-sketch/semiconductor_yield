import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import impact_summary as isum


def test_defect_catch_rate_counts_any_defect_prediction_as_a_catch():
    classes = ["none", "Center", "Scratch"]
    # 10 real Center wafers: 6 correctly predicted Center, 3 predicted Scratch
    # (still "caught" -- some defect flagged), 1 predicted none (missed)
    cm = [
        [100, 0, 0],
        [1, 6, 3],
        [0, 0, 5],
    ]
    metrics = {"classes": classes, "test_confusion_matrix": cm}
    rate = isum.defect_catch_rate(metrics)
    # true defects: row 1 (Center, 10) + row 2 (Scratch, 5) = 15
    # caught (predicted != none): (6+3) + (5) = 14
    assert abs(rate - 14 / 15) < 1e-9


def test_defect_catch_rate_none_when_no_real_defects_in_test_set():
    metrics = {"classes": ["none", "Center"], "test_confusion_matrix": [[100, 0], [0, 0]]}
    assert isum.defect_catch_rate(metrics) is None


def test_build_summary_handles_missing_pieces_gracefully():
    """Every optional dependency (untrained CNN, untrained baseline, no
    quality-risk mapping) must degrade gracefully, not crash -- this
    module composes real outputs, and any of them can legitimately be
    absent (e.g. a fresh clone with no WM-811K data)."""
    baseline_scenario = {
        "optimization": {"status": "optimal", "release_plan": {1: 10, 2: 5}},
        "capacity": {"bottleneck": "Diffusion", "stations": [{"stngrp": "Diffusion", "utilization": 0.776}]},
    }
    integration = {"backlog_delta_from_yield_loss": None, "capacity_plan_unadjusted_backlog": None,
                   "quality_risk": None, "capacity_bottleneck_station": "Diffusion", "same_station_both_lenses": None}
    cnn_metrics = {"status": "not_trained"}
    baseline_metrics = {"status": "not_trained"}
    arch = {"bottleneck_wait_delta_fraction": None}

    summary = isum.build_summary(baseline_scenario, 390.0, integration, cnn_metrics, baseline_metrics, arch)
    assert summary["status"] == "optimal"
    assert summary["pct_real_demand_met"] == 15 / 390.0
    assert summary["defect_catch_rate"] is None
    assert summary["cnn_beats_baseline_by"] is None
    assert isinstance(summary["narrative"], str)
    assert len(summary["narrative"]) > 0


def test_narrative_mentions_quality_risk_only_when_it_differs_from_bottleneck():
    baseline_scenario = {
        "optimization": {"status": "optimal", "release_plan": {1: 19}},
        "capacity": {"bottleneck": "Diffusion", "stations": [{"stngrp": "Diffusion", "utilization": 0.776}]},
    }
    integration_same = {
        "backlog_delta_from_yield_loss": None, "capacity_plan_unadjusted_backlog": None,
        "quality_risk": {"top_quality_risk_station": "Diffusion"},
        "capacity_bottleneck_station": "Diffusion", "same_station_both_lenses": True,
    }
    integration_diff = {**integration_same, "quality_risk": {"top_quality_risk_station": "Wet_Etch"}}
    arch = {"bottleneck_wait_delta_fraction": None}
    empty = {"status": "not_trained"}

    same = isum.build_summary(baseline_scenario, 390.0, integration_same, empty, empty, arch)
    diff = isum.build_summary(baseline_scenario, 390.0, integration_diff, empty, empty, arch)
    assert "Wet_Etch" not in same["narrative"]
    assert "Wet_Etch" in diff["narrative"]


def test_narrative_never_starts_a_sentence_with_a_lowercase_letter():
    """Regression test: the catch-rate and cnn-vs-baseline sentences used to
    be appended as two separate parts, joined with a space, which produced
    grammar like "...as defective. beating a hand-engineered baseline..."
    -- a lowercase word right after a period. They must now read as one
    sentence (or the baseline clause must start its own capitalized one)."""
    baseline_scenario = {
        "optimization": {"status": "optimal", "release_plan": {1: 19}},
        "capacity": {"bottleneck": "Diffusion", "stations": [{"stngrp": "Diffusion", "utilization": 0.776}]},
    }
    integration = {
        "backlog_delta_from_yield_loss": None, "capacity_plan_unadjusted_backlog": None,
        "quality_risk": None, "capacity_bottleneck_station": "Diffusion", "same_station_both_lenses": None,
    }
    cnn_metrics = {
        "status": "trained", "test_macro_f1": 0.70,
        "classes": ["none", "Center"],
        "test_confusion_matrix": [[100, 0], [2, 8]],
    }
    baseline_metrics = {"status": "trained", "test_macro_f1": 0.65}
    arch = {"bottleneck_wait_delta_fraction": None}

    summary = isum.build_summary(baseline_scenario, 390.0, integration, cnn_metrics, baseline_metrics, arch)
    assert "beating" in summary["narrative"]
    # no ". <lowercase letter>" anywhere in the composed narrative
    assert not re.search(r"\.\s+[a-z]", summary["narrative"]), summary["narrative"]
