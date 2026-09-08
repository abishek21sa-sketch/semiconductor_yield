"""
Yield-risk layer: real SECOM fab sensor data (UCI #179) -> cross-validated
classifier + classical semiconductor yield theory + SPC monitoring.

Every number this module returns is computed from the real dataset at call
time -- nothing here is a hand-typed placeholder.
"""
import math
import re
from pathlib import Path
from functools import lru_cache

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    average_precision_score, confusion_matrix, precision_recall_curve,
    roc_auc_score, roc_curve,
)
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import Pipeline

DATA = Path(__file__).resolve().parent.parent / "data"
RANDOM_STATE = 42


def _load_raw():
    X = pd.read_csv(DATA / "secom.data", sep=r"\s+", header=None)
    X.columns = [f"sensor_{i + 1:03d}" for i in range(X.shape[1])]

    pat = re.compile(r'^(-?\d+)\s+"([^"]+)"\s*$')
    rows = []
    with open(DATA / "secom_labels.data") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            m = pat.match(line)
            rows.append((int(m.group(1)), m.group(2)))
    labels = pd.DataFrame(rows, columns=["label_raw", "timestamp"])
    labels["timestamp"] = pd.to_datetime(labels["timestamp"], format="%d/%m/%Y %H:%M:%S")
    labels["fail"] = (labels["label_raw"] == 1).astype(int)

    df = X.copy()
    df["fail"] = labels["fail"].values
    df["timestamp"] = labels["timestamp"].values
    return df


def _clean(df):
    feature_cols = [c for c in df.columns if c.startswith("sensor_")]
    missing_frac = df[feature_cols].isna().mean()
    keep = missing_frac[missing_frac <= 0.45].index.tolist()
    dropped_missing = len(feature_cols) - len(keep)

    Xc = df[keep]
    variances = Xc.var(numeric_only=True, skipna=True)
    nonconstant = variances[variances > 1e-12].index.tolist()
    dropped_constant = len(keep) - len(nonconstant)
    return df[nonconstant], dropped_missing, dropped_constant


@lru_cache(maxsize=1)
def run_full_analysis():
    """Runs the full real-data pipeline once and caches the result in memory."""
    df = _load_raw()
    Xc, dropped_missing, dropped_constant = _clean(df)
    y = df["fail"].values
    n_lots, n_fails = len(df), int(df["fail"].sum())

    rf = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("clf", RandomForestClassifier(
            n_estimators=400, min_samples_leaf=2,
            class_weight="balanced_subsample", random_state=RANDOM_STATE, n_jobs=-1,
        )),
    ])
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
    proba = cross_val_predict(rf, Xc, y, cv=skf, method="predict_proba", n_jobs=-1)[:, 1]

    roc_auc = roc_auc_score(y, proba)
    pr_auc = average_precision_score(y, proba)
    fpr, tpr, _ = roc_curve(y, proba)
    prec, rec, pr_thresh = precision_recall_curve(y, proba)

    def metrics_at(t):
        pred = (proba >= t).astype(int)
        tn, fp, fn, tp = confusion_matrix(y, pred).ravel()
        return dict(
            threshold=float(t), tp=int(tp), fp=int(fp), fn=int(fn), tn=int(tn),
            precision=float(tp / (tp + fp)) if (tp + fp) else 0.0,
            recall=float(tp / (tp + fn)) if (tp + fn) else 0.0,
        )

    best_t, best_p = 0.5, -1
    for p_, r_, t_ in zip(prec[:-1], rec[:-1], pr_thresh):
        if r_ >= 0.5 and p_ > best_p:
            best_p, best_t = p_, t_

    rf_full = rf.fit(Xc, y)
    importances = rf_full.named_steps["clf"].feature_importances_
    top_sensors = pd.Series(importances, index=Xc.columns).sort_values(ascending=False).head(15)

    top_sensor_name = top_sensors.index[0]
    sensor_vals = df[top_sensor_name]
    pass_vals = sensor_vals[df["fail"] == 0].dropna()
    mu, sigma = float(pass_vals.mean()), float(pass_vals.std())
    ucl, lcl = mu + 3 * sigma, mu - 3 * sigma

    plot_df = df[["timestamp", top_sensor_name, "fail"]].dropna(subset=[top_sensor_name]).sort_values("timestamp")
    spc_points = [
        {"t": r.timestamp.isoformat(), "v": float(getattr(r, top_sensor_name)), "fail": int(r.fail)}
        for r in plot_df.itertuples()
    ]

    top5 = top_sensors.head(5).index.tolist()
    oob = pd.DataFrame(index=df.index)
    for s in top5:
        vals = df[s]
        pv = vals[df["fail"] == 0].dropna()
        m, sd = pv.mean(), pv.std()
        oob[s] = (vals < m - 3 * sd) | (vals > m + 3 * sd)
    any_oob = oob.any(axis=1)
    fails_with_oob = int((any_oob & (df["fail"] == 1)).sum())
    passes_with_oob = int((any_oob & (df["fail"] == 0)).sum())

    df_sorted = df.sort_values("timestamp").reset_index(drop=True)
    df_sorted["week"] = df_sorted["timestamp"].dt.to_period("W").dt.start_time
    weekly = df_sorted.groupby("week").agg(n=("fail", "size"), fails=("fail", "sum")).reset_index()
    weekly["yield"] = 1 - weekly["fails"] / weekly["n"]
    yield_trend = [
        {"week": w.isoformat(), "n": int(n), "fails": int(f), "yield": float(yy)}
        for w, n, f, yy in zip(weekly["week"], weekly["n"], weekly["fails"], weekly["yield"])
    ]

    step = max(1, len(fpr) // 200)
    step2 = max(1, len(prec) // 200)
    return {
        "meta": {
            "dataset": "SECOM (UCI ML Repository #179)",
            "source_url": "https://archive.ics.uci.edu/dataset/179/secom",
            "n_lots": n_lots, "n_fails": n_fails, "yield_rate": 1 - n_fails / n_lots,
            "n_sensors_raw": len(df.columns) - 2,  # minus the fail/timestamp columns
            "n_sensors_used": Xc.shape[1], "dropped_missing": dropped_missing,
            "dropped_constant": dropped_constant,
            "date_range": [plot_df["timestamp"].min().isoformat(), plot_df["timestamp"].max().isoformat()],
        },
        "model": {
            "type": "Random Forest, 400 trees, class-balanced, 5-fold stratified CV (out-of-fold predictions)",
            "roc_auc": roc_auc, "pr_auc": pr_auc,
            "majority_class_accuracy": 1 - n_fails / n_lots,
            "roc_curve": {"fpr": fpr[::step].tolist(), "tpr": tpr[::step].tolist()},
            "pr_curve": {"precision": prec[::step2].tolist(), "recall": rec[::step2].tolist()},
            "operating_points": {"default_0.5": metrics_at(0.5), "recall_ge_50pct": metrics_at(best_t)},
        },
        "top_sensors": [{"sensor": s, "importance": float(v)} for s, v in top_sensors.items()],
        "spc": {
            "sensor": top_sensor_name, "mu": mu, "sigma": sigma, "ucl": ucl, "lcl": lcl,
            "n_out_of_band": int(((sensor_vals < lcl) | (sensor_vals > ucl)).sum()),
            "points": spc_points,
        },
        "top5_oob_signal": {
            "sensors": top5, "fails_with_any_oob": fails_with_oob,
            "fail_oob_rate": fails_with_oob / n_fails if n_fails else 0.0,
            "passes_with_any_oob": passes_with_oob,
            "pass_oob_rate": passes_with_oob / (n_lots - n_fails),
        },
        "yield_trend": yield_trend,
    }


# ---------------------------------------------------------------------------
# Classical semiconductor yield theory (Poisson / Murphy defect-density models)
# Standard formulas from semiconductor yield engineering literature.
# ---------------------------------------------------------------------------

def poisson_yield(defect_density_per_cm2: float, die_area_cm2: float) -> float:
    """Y = exp(-D0 * A). Simplest classical model; assumes uniform defect
    distribution across the wafer -- tends to under-predict yield for large die."""
    return math.exp(-defect_density_per_cm2 * die_area_cm2)


def murphy_yield(defect_density_per_cm2: float, die_area_cm2: float) -> float:
    """Murphy's model: Y = ((1 - exp(-D0*A)) / (D0*A))^2. Accounts for defect
    clustering across the wafer -- the standard textbook improvement on the
    naive Poisson model for real fab defect distributions."""
    d0a = defect_density_per_cm2 * die_area_cm2
    if d0a <= 1e-12:
        return 1.0
    return ((1 - math.exp(-d0a)) / d0a) ** 2


def negative_binomial_yield(defect_density_per_cm2: float, die_area_cm2: float, cluster_alpha: float = 2.0) -> float:
    """Negative-binomial (Seeds/NBD) model: Y = (1 + D0*A/alpha)^(-alpha).
    alpha is a clustering parameter (lower alpha = more clustered defects);
    alpha in the 1-5 range is typical for real fab defect data."""
    d0a = defect_density_per_cm2 * die_area_cm2
    return (1 + d0a / cluster_alpha) ** (-cluster_alpha)


def yield_model_curve(die_areas_cm2, defect_density_per_cm2, cluster_alpha=2.0):
    return [
        {
            "die_area_cm2": a,
            "poisson": poisson_yield(defect_density_per_cm2, a),
            "murphy": murphy_yield(defect_density_per_cm2, a),
            "negative_binomial": negative_binomial_yield(defect_density_per_cm2, a, cluster_alpha),
        }
        for a in die_areas_cm2
    ]
