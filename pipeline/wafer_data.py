"""
Loads the real WM-811K wafer defect-map dataset (811,457 real wafer maps from
real fab lots; 172,950 of them human-labeled into 9 real defect-pattern
classes) and prepares it for CNN training/inference.

The raw file (data/wm811k/LSWMD.pkl, ~2.1GB, gitignored -- see
data/wm811k/ATTRIBUTION.md) was pickled under Python 2 with a pandas version
from ~2019. Two compatibility issues stop modern pandas from reading it
directly: `pandas.indexes` was renamed to `pandas.core.indexes` years ago,
and the raw numpy byte data needs latin1 decoding (a Python 2 pickle marker).
_LegacyUnpickler below is a real fix for both, not a workaround that silently
drops data.
"""
import importlib
import pickle
from pathlib import Path

import numpy as np
from scipy.ndimage import zoom

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "wm811k"
RAW_PATH = DATA_DIR / "LSWMD.pkl"

# The 9 real classes: 8 real defect patterns the WM-811K authors' domain
# experts labeled, plus "none" (a wafer a human reviewed and found normal).
# Fixed order everywhere (label <-> index mapping, confusion matrix axes).
CLASSES = ["none", "Center", "Donut", "Edge-Loc", "Edge-Ring", "Loc", "Near-full", "Random", "Scratch"]
CLASS_TO_IDX = {c: i for i, c in enumerate(CLASSES)}

WAFER_SIZE = 64  # fixed square size every real wafer map is resized to


class _LegacyUnpickler(pickle.Unpickler):
    """Redirects the pre-0.20 `pandas.indexes.*` module path (used when this
    file was written) to its modern `pandas.core.indexes.*` location."""

    def find_class(self, module, name):
        if module.startswith("pandas.indexes"):
            candidates = [
                "pandas.core.indexes" + module[len("pandas.indexes"):],
                "pandas.core.indexes.base",
                "pandas.core.indexes.api",
                "pandas.core.indexes.range",
                "pandas.core.indexes.multi",
            ]
            for candidate in candidates:
                try:
                    mod = importlib.import_module(candidate)
                except ImportError:
                    continue
                if hasattr(mod, name):
                    return getattr(mod, name)
        if module == "pandas.core.index":
            module = "pandas.core.indexes.base"
        return super().find_class(module, name)


def load_raw_dataframe():
    """Real WM-811K data, exactly as published -- no rows dropped, no
    relabeling. Requires data/wm811k/LSWMD.pkl to exist locally (not in git,
    ~2.1GB; see data/wm811k/ATTRIBUTION.md for where to get it)."""
    if not RAW_PATH.exists():
        raise FileNotFoundError(
            f"{RAW_PATH} is missing. Download WM-811K (LSWMD.pkl) from Kaggle "
            "and place it there -- see data/wm811k/ATTRIBUTION.md."
        )
    with open(RAW_PATH, "rb") as f:
        return _LegacyUnpickler(f, encoding="latin1").load()


def _is_labeled(failure_type):
    return isinstance(failure_type, np.ndarray) and failure_type.size > 0


def load_labeled_wafers():
    """The 172,950 real wafers a human actually labeled -- the 638,507
    unlabeled wafers are real too but unusable for supervised training.
    Returns a DataFrame with a clean `label` string column (one of CLASSES)
    in place of the raw nested-array failureType field."""
    df = load_raw_dataframe()
    labeled = df[df.failureType.apply(_is_labeled)].copy()
    labeled["label"] = labeled.failureType.apply(lambda x: str(x[0][0]))
    unknown = set(labeled["label"]) - set(CLASSES)
    if unknown:
        raise ValueError(f"Unexpected label(s) in real data not in CLASSES: {unknown}")
    return labeled[["waferMap", "dieSize", "lotName", "label"]].reset_index(drop=True)


def resize_wafer_map(wafer_map, size=WAFER_SIZE):
    """Nearest-neighbor resize (order=0) so the categorical values
    {0=no die, 1=pass, 2=fail} are preserved exactly -- linear/cubic
    interpolation would invent nonsense intermediate values between
    discrete categories that were never in the real data."""
    h, w = wafer_map.shape
    return zoom(wafer_map, (size / h, size / w), order=0)


def encode_wafer_map(wafer_map, size=WAFER_SIZE):
    """Resizes to a fixed size and encodes as 2 channels (die-present mask,
    fail mask) rather than feeding the raw {0,1,2} ordinals to a CNN, which
    would falsely imply fail(2) > pass(1) > absent(0) as a magnitude."""
    resized = resize_wafer_map(wafer_map, size)
    die_present = (resized >= 1).astype(np.float32)
    fail = (resized == 2).astype(np.float32)
    return np.stack([die_present, fail], axis=0)  # (2, size, size)


def stratified_split(labeled_df, seed=13, train_frac=0.8, val_frac=0.1):
    """A class-balanced 80/10/10 split we cut ourselves, not the dataset's
    own trianTestLabel field -- that field is real (each row really was
    marked Test/Training by WM-811K's creators) but isn't class-stratified
    and skews 69% Test / 31% Training, which isn't a standard ML split. This
    choice is stated here rather than silently substituted."""
    rng = np.random.default_rng(seed)
    train_idx, val_idx, test_idx = [], [], []
    for label in CLASSES:
        idx = labeled_df.index[labeled_df.label == label].to_numpy().copy()
        rng.shuffle(idx)
        n = len(idx)
        n_train = int(n * train_frac)
        n_val = int(n * val_frac)
        train_idx.append(idx[:n_train])
        val_idx.append(idx[n_train:n_train + n_val])
        test_idx.append(idx[n_train + n_val:])
    # Original labeled_df index deliberately kept (not reset) on each output:
    # it's how callers/tests can verify the three splits are genuinely
    # index-disjoint -- the real data has a handful of rows (15 of 172,950)
    # with byte-identical wafer maps under the same lot name, so a
    # content-based identity check isn't reliable, but the index always is.
    return (
        labeled_df.loc[np.concatenate(train_idx)],
        labeled_df.loc[np.concatenate(val_idx)],
        labeled_df.loc[np.concatenate(test_idx)],
    )
