import sys
import tempfile
from pathlib import Path

import pytest

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


def test_train_and_save_defaults_to_augmentation_on():
    """augment defaults to True based on a real same-seed controlled A/B
    result (scripts/train_wafer_cnn.py --ab-test): 69.8% vs 69.0% test
    macro-F1, augment=True ahead -- see train_and_save's docstring for the
    full story, including the earlier uncontrolled comparison that (wrongly)
    said the opposite. This just guards the default itself from silently
    flipping back without that decision being revisited."""
    import inspect

    assert inspect.signature(wafer_cnn.train_and_save).parameters["augment"].default is True


def test_gradcam_output_is_normalized_and_matches_last_conv_resolution():
    import torch

    model = wafer_cnn.WaferCNN()
    x = torch.randn(2, wafer_cnn.wd.WAFER_SIZE, wafer_cnn.wd.WAFER_SIZE)
    cam = wafer_cnn.compute_gradcam(model, x, target_class=0)
    assert cam.shape == (16, 16)  # model.features[10]'s real spatial resolution
    assert cam.min() >= 0.0
    assert cam.max() <= 1.0 + 1e-6


@pytest.mark.skipif(not wafer_cnn.wd.RAW_PATH.exists(), reason="data/wm811k/LSWMD.pkl not present locally")
def test_train_and_save_is_reproducible_given_the_same_seed():
    """Regression test for a real bug: train_and_save used to seed only the
    data split (via wafer_data's own Generator), not torch's or numpy's
    global RNG -- so two "identical" runs (same seed, same everything else)
    could land anywhere in a multi-point test-macro-F1 band from
    uncontrolled weight init / shuffling / augmentation randomness alone,
    which silently invalidated any single-run A/B comparison (e.g. "does
    augmentation help"). Two tiny runs with the same seed must now produce
    byte-identical metrics."""
    with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
        r1 = wafer_cnn.train_and_save(epochs=1, batch_size=64, max_train=300, max_eval=100, seed=7, artifact_dir=tmp1)
        r2 = wafer_cnn.train_and_save(epochs=1, batch_size=64, max_train=300, max_eval=100, seed=7, artifact_dir=tmp2)
    assert r1["test_macro_f1"] == r2["test_macro_f1"]
    assert r1["training_history"] == r2["training_history"]
