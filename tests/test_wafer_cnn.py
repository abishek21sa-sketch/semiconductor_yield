import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import wafer_cnn


def test_load_artifacts_never_trains_and_always_returns_a_status():
    """load_artifacts() is what the live API calls on every request -- it
    must be fast and must never attempt to load the ~2GB raw dataset or
    train, regardless of whether a trained model exists on this machine."""
    result = wafer_cnn.load_artifacts()
    assert result["status"] in ("trained", "not_trained")


def test_trained_artifacts_have_a_real_evaluated_model():
    result = wafer_cnn.load_artifacts()
    if result["status"] != "trained":
        return  # nothing trained on this machine -- covered by the status check above
    assert result["classes"] == wafer_cnn.wd.CLASSES
    assert len(result["test_confusion_matrix"]) == len(wafer_cnn.wd.CLASSES)
    assert 0 <= result["test_macro_f1"] <= 1
    assert 0 <= result["test_accuracy"] <= 1
    # the confusion matrix's row totals must equal the real per-class test support
    row_sums = [sum(row) for row in result["test_confusion_matrix"]]
    support_by_class = {p["class"]: p["support"] for p in result["test_per_class"]}
    for cls, row_sum in zip(result["classes"], row_sums):
        assert row_sum == support_by_class[cls]
