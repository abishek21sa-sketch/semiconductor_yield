import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import wafer_data as wd

# These tests need the real ~2GB WM-811K file, which is gitignored and not
# present in CI or a fresh clone -- skip rather than fail when it's missing,
# same spirit as the license-gated MILP tests skip real solving without a
# Gurobi license.
pytestmark = pytest.mark.skipif(not wd.RAW_PATH.exists(), reason="data/wm811k/LSWMD.pkl not present locally")


@pytest.fixture(scope="module")
def labeled():
    return wd.load_labeled_wafers()


def test_labeled_count_and_classes_match_published_dataset(labeled):
    # The real, published WM-811K labeled count -- if this drifts, either the
    # source file changed or our filtering logic broke.
    assert len(labeled) == 172950
    assert set(labeled.label.unique()) == set(wd.CLASSES)


def test_stratified_split_has_no_overlap_and_covers_everything(labeled):
    train, val, test = wd.stratified_split(labeled)
    assert len(train) + len(val) + len(test) == len(labeled)
    # Real DataFrame index (deliberately preserved by stratified_split, not
    # reset) is the reliable disjointness check -- a content-based key
    # (lotName + wafer bytes) isn't: 15 of the real 172,950 labeled wafers
    # are byte-identical duplicates under the same lot name.
    train_idx, val_idx, test_idx = set(train.index), set(val.index), set(test.index)
    assert len(train_idx & val_idx) == 0
    assert len(train_idx & test_idx) == 0
    assert len(val_idx & test_idx) == 0
    assert train_idx | val_idx | test_idx == set(labeled.index)


def test_stratified_split_is_class_balanced(labeled):
    train, _, _ = wd.stratified_split(labeled, train_frac=0.8, val_frac=0.1)
    for cls in wd.CLASSES:
        real_frac = (labeled.label == cls).sum() / len(labeled)
        train_frac = (train.label == cls).sum() / len(train)
        assert abs(real_frac - train_frac) < 0.01, f"{cls}: real {real_frac:.4f} vs train {train_frac:.4f}"


def test_resize_preserves_categorical_values(labeled):
    wafer_map = labeled.waferMap.iloc[0]
    resized = wd.resize_wafer_map(wafer_map, size=64)
    assert resized.shape == (64, 64)
    # nearest-neighbor resize must never invent a value outside the real set
    assert set(np.unique(resized)) <= {0, 1, 2}


def test_encode_wafer_map_shape_and_channels(labeled):
    wafer_map = labeled.waferMap.iloc[0]
    encoded = wd.encode_wafer_map(wafer_map, size=64)
    assert encoded.shape == (2, 64, 64)
    assert encoded.dtype == np.float32
    # fail-die pixels are a subset of die-present pixels
    assert np.all(encoded[0][encoded[1] == 1] == 1)
