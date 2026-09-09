"""
A hand-engineered-feature baseline classifier for the real WM-811K wafer
defect classification task -- the kind of features used in pre-deep-
learning wafer-map defect literature (density, spatial centroid, radial
spread, edge concentration, connected-component structure of the failed
dies). Trained and evaluated on the exact same real split as the CNN
(pipeline/wafer_cnn.py, via wafer_data.prepare_training_split), so the
macro-F1 gap between the two is a genuine "does the CNN's spatial modeling
actually earn its complexity" comparison, not two different splits that
happen to look similar.
"""
import json
import math
import time

import numpy as np
from scipy.ndimage import label as connected_components
from sklearn.ensemble import RandomForestClassifier

from pipeline import wafer_data as wd
from pipeline.wafer_cnn import _confusion_matrix, _precision_recall_f1

FEATURE_NAMES = [
    "fail_density", "centroid_radius", "radial_std", "edge_fraction",
    "n_components_norm", "largest_component_fraction",
]

METRICS_PATH = wd.DATA_DIR / "wafer_baseline_metrics.json"


def extract_features(wafer_map: np.ndarray) -> np.ndarray:
    """6 real hand-engineered features from one real wafer map's die grid."""
    h, w = wafer_map.shape
    cy, cx = (h - 1) / 2.0, (w - 1) / 2.0
    max_r = math.hypot(cy, cx) or 1.0
    die_mask = wafer_map >= 1
    fail_mask = wafer_map == 2
    n_die = int(die_mask.sum())
    n_fail = int(fail_mask.sum())

    if n_die == 0:
        return np.zeros(len(FEATURE_NAMES), dtype=np.float32)

    fail_density = n_fail / n_die

    if n_fail == 0:
        centroid_radius = radial_std = edge_fraction = 0.0
        n_components_norm = largest_component_fraction = 0.0
    else:
        ys, xs = np.nonzero(fail_mask)
        r = np.sqrt((ys - cy) ** 2 + (xs - cx) ** 2) / max_r
        centroid_radius = math.hypot(ys.mean() - cy, xs.mean() - cx) / max_r
        radial_std = float(r.std())
        edge_fraction = float((r > 0.8).mean())
        labeled_arr, n_comp = connected_components(fail_mask)
        sizes = np.bincount(labeled_arr.ravel())[1:]  # drop background label 0
        n_components_norm = n_comp / n_fail
        largest_component_fraction = float(sizes.max() / n_fail) if len(sizes) else 0.0

    return np.array([
        fail_density, centroid_radius, radial_std, edge_fraction,
        n_components_norm, largest_component_fraction,
    ], dtype=np.float32)


def train_and_evaluate(seed=13, max_none_train=25000, log=print, metrics_path=None):
    """Trains a class-weighted RandomForest on hand-engineered features
    over the exact same real train/val/test split as the CNN, and returns
    the same shape of metrics dict (macro_f1, per_class, confusion_matrix)
    for a direct side-by-side comparison in the API/frontend. Writes to
    metrics_path (default METRICS_PATH, the real served location) -- pass
    a throwaway path for a smoke test, same pattern as wafer_cnn.py."""
    t0 = time.time()
    labeled = wd.load_labeled_wafers()
    train_df, val_df, test_df = wd.prepare_training_split(labeled, seed=seed, max_none_train=max_none_train)
    log(f"Extracting hand-engineered features for {len(train_df)} train / {len(test_df)} test real wafers...")

    X_train = np.stack([extract_features(wm) for wm in train_df.waferMap])
    y_train = np.array([wd.CLASS_TO_IDX[l] for l in train_df.label])
    X_test = np.stack([extract_features(wm) for wm in test_df.waferMap])
    y_test = np.array([wd.CLASS_TO_IDX[l] for l in test_df.label])

    # n_jobs=1: this machine runs other CPU-heavy work concurrently, and
    # joblib's multiprocess backend has crashed under memory pressure here
    # before -- 6 features / ~45K rows trains fast single-threaded anyway.
    clf = RandomForestClassifier(n_estimators=300, class_weight="balanced", random_state=seed, n_jobs=1)
    clf.fit(X_train, y_train)
    y_pred = clf.predict(X_test)

    cm = _confusion_matrix(y_test.tolist(), y_pred.tolist(), len(wd.CLASSES))
    per_class, macro_f1 = _precision_recall_f1(cm)
    accuracy = float(np.mean(y_test == y_pred))
    log(f"Baseline done in {time.time()-t0:.1f}s: macro_f1={macro_f1:.4f} accuracy={accuracy:.4f}")

    metrics = {
        "status": "trained",
        "model": "RandomForestClassifier (hand-engineered features)",
        "feature_names": FEATURE_NAMES,
        "feature_importances": {n: float(v) for n, v in zip(FEATURE_NAMES, clf.feature_importances_)},
        "n_train": len(train_df), "n_test": len(test_df),
        "test_confusion_matrix": cm.tolist(),
        "test_per_class": per_class,
        "test_macro_f1": macro_f1,
        "test_accuracy": accuracy,
        "train_seconds": time.time() - t0,
    }
    path = metrics_path or METRICS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metrics, indent=2))
    return metrics


def load_artifacts():
    """What the live API calls -- fast, never trains. Same not_trained
    contract as wafer_cnn.load_artifacts()."""
    if not METRICS_PATH.exists():
        return {"status": "not_trained", "message": "Run scripts/train_wafer_cnn.py first (needs data/wm811k/LSWMD.pkl)."}
    return json.loads(METRICS_PATH.read_text())
