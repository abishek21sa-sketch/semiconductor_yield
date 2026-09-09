"""
One headline "if you deployed everything this app recommends" summary,
composed entirely from numbers the other pipeline stages already computed
-- no new fabricated math, no invented dollar figures or unit economics.
The one genuinely new derived number here (defect_catch_rate) is a
straightforward re-aggregation of the CNN's own real confusion matrix, not
a new model or assumption.

This exists because the individual pipeline stages, however real each one
is on its own, read as separate facts (a yield rate here, a bottleneck %
there, a macro-F1 somewhere else) unless something ties them into one
story. This module is that tie -- not a new computation, a synthesis of
existing ones.
"""


def defect_catch_rate(cnn_metrics: dict) -> float | None:
    """Of all real test-set wafers with an actual defect (true label !=
    "none"), what fraction did the CNN flag as having SOME defect
    (predicted label != "none", regardless of which specific type)? This
    is the operationally relevant number for a triage/rework-routing use
    case -- "did we catch that something's wrong" -- distinct from
    macro-F1, which weights getting the EXACT class right. Computed
    directly from the CNN's own real confusion matrix, not asserted."""
    classes = cnn_metrics.get("classes")
    cm = cnn_metrics.get("test_confusion_matrix")
    if not classes or not cm:
        return None
    none_idx = classes.index("none")
    true_defect_total = sum(cm[i][j] for i in range(len(classes)) for j in range(len(classes)) if i != none_idx)
    if true_defect_total == 0:
        return None
    caught = sum(cm[i][j] for i in range(len(classes)) for j in range(len(classes)) if i != none_idx and j != none_idx)
    return caught / true_defect_total


def build_summary(baseline_scenario: dict, total_real_weekly_demand: float, integration: dict,
                   cnn_metrics: dict, baseline_metrics: dict, archetype_comparison: dict) -> dict:
    """Pure composition -- every field here is read from a result some
    other pipeline module already computed and returned; this function
    adds no new solver calls of its own (defect_catch_rate is the one
    exception, a pure re-aggregation of already-real data)."""
    opt = baseline_scenario["optimization"]
    cap = baseline_scenario["capacity"]
    total_released = sum(opt["release_plan"].values()) if opt.get("status") == "optimal" else 0
    pct_demand_met = total_released / total_real_weekly_demand if total_real_weekly_demand else None

    catch_rate = defect_catch_rate(cnn_metrics) if cnn_metrics.get("status") == "trained" else None

    yield_backlog_pct = None
    if integration.get("backlog_delta_from_yield_loss") is not None and integration.get("capacity_plan_unadjusted_backlog"):
        yield_backlog_pct = integration["backlog_delta_from_yield_loss"] / integration["capacity_plan_unadjusted_backlog"]

    hvlm_wait_pct = archetype_comparison.get("bottleneck_wait_delta_fraction")

    cnn_f1 = cnn_metrics.get("test_macro_f1")
    baseline_f1 = baseline_metrics.get("test_macro_f1")
    cnn_vs_baseline = (cnn_f1 - baseline_f1) if cnn_f1 is not None and baseline_f1 is not None else None

    narrative = _narrative(
        pct_demand_met, cap.get("bottleneck"), _bottleneck_util(cap),
        yield_backlog_pct, integration.get("quality_risk"), integration.get("capacity_bottleneck_station"),
        catch_rate, cnn_f1, baseline_f1, cnn_vs_baseline, hvlm_wait_pct,
    )

    return {
        "status": "optimal",
        "pct_real_demand_met": pct_demand_met,
        "capacity_bottleneck": cap.get("bottleneck"),
        "capacity_bottleneck_utilization": _bottleneck_util(cap),
        "yield_adjusted_backlog_increase_fraction": yield_backlog_pct,
        "top_quality_risk_station": (integration.get("quality_risk") or {}).get("top_quality_risk_station"),
        "quality_risk_differs_from_capacity_bottleneck": integration.get("same_station_both_lenses") is False,
        "defect_catch_rate": catch_rate,
        "cnn_macro_f1": cnn_f1,
        "baseline_macro_f1": baseline_f1,
        "cnn_beats_baseline_by": cnn_vs_baseline,
        "hvlm_bottleneck_wait_increase_fraction": hvlm_wait_pct,
        "narrative": narrative,
    }


def _bottleneck_util(cap: dict) -> float | None:
    bn = cap.get("bottleneck")
    for s in cap.get("stations", []):
        if s["stngrp"] == bn:
            return s["utilization"]
    return None


def _narrative(pct_demand_met, bottleneck, bn_util, yield_backlog_pct, quality_risk, quality_bottleneck_match,
               catch_rate, cnn_f1, baseline_f1, cnn_vs_baseline, hvlm_wait_pct) -> str:
    parts = []
    if pct_demand_met is not None and bottleneck and bn_util is not None:
        parts.append(
            f"At real order demand, this fab can meet only {pct_demand_met:.0%} of total weekly volume, "
            f"bottlenecked at {bottleneck} ({bn_util:.0%} utilized)."
        )
    if yield_backlog_pct is not None:
        parts.append(
            f"Netting out the real measured SECOM yield rate against this plan increases the 26-week "
            f"backlog by {yield_backlog_pct:.1%}."
        )
    if quality_risk and quality_risk.get("top_quality_risk_station") and quality_risk["top_quality_risk_station"] != bottleneck:
        parts.append(
            f"The real WM-811K defect-type distribution points at {quality_risk['top_quality_risk_station']} "
            f"as the top quality-risk area -- a different station than the capacity bottleneck, so fixing "
            f"one wouldn't fix the other."
        )
    if catch_rate is not None:
        sentence = f"The trained CNN correctly flags {catch_rate:.0%} of real defective wafers as defective"
        if cnn_vs_baseline is not None:
            sentence += (
                f", beating a hand-engineered-feature baseline by {cnn_vs_baseline:+.2f} macro-F1 "
                f"({cnn_f1:.2f} vs {baseline_f1:.2f})"
            )
        parts.append(sentence + ".")
    elif cnn_vs_baseline is not None:
        parts.append(
            f"The trained CNN beats a hand-engineered-feature baseline by {cnn_vs_baseline:+.2f} macro-F1 "
            f"({cnn_f1:.2f} vs {baseline_f1:.2f})."
        )
    if hvlm_wait_pct is not None and hvlm_wait_pct > 0:
        parts.append(
            f"Concentrating the same real total demand onto fewer products (the HVLM archetype) makes "
            f"bottleneck queueing {hvlm_wait_pct:.0%} worse using the exact same real tools."
        )
    return " ".join(parts)
