"""
A real CNN classifier over real WM-811K wafer defect maps -- 9 classes (8
real defect patterns + "none"), trained with class-weighted loss against the
severe real class imbalance (147,431 "none" vs 149 "Near-full").

Training is CPU-only (no GPU on this machine) and materializing all 172,950
wafer maps pre-resized to a fixed size up front would need ~5.7GB (vs ~230MB
for the raw variable-size arrays), so WaferMapDataset resizes/encodes each
sample lazily in __getitem__ instead of precomputing a big tensor.

This is a train-once, serve-many module: training takes real minutes, so
train_and_save() is run standalone (see scripts/train_wafer_cnn.py), and the
API only ever calls load_artifacts() at startup, never trains on request.
"""
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

from pipeline import wafer_data as wd

ARTIFACT_DIR = wd.DATA_DIR
MODEL_PATH = ARTIFACT_DIR / "wafer_cnn_model.pt"
METRICS_PATH = ARTIFACT_DIR / "wafer_cnn_metrics.json"
SAMPLES_PATH = ARTIFACT_DIR / "wafer_cnn_samples.json"


class WaferMapDataset(Dataset):
    """Lazily resizes+encodes each real wafer map on access -- keeps peak
    memory to one batch at a time instead of the whole dataset pre-resized."""

    def __init__(self, df):
        self.wafer_maps = df.waferMap.to_numpy()
        self.labels = np.array([wd.CLASS_TO_IDX[l] for l in df.label], dtype=np.int64)

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, i):
        x = wd.encode_wafer_map(self.wafer_maps[i])
        return torch.from_numpy(x), int(self.labels[i])


class WaferCNN(nn.Module):
    """Small conv net: 3 conv blocks (64x64 -> 8x8) + 2 FC layers, ~640K
    params -- small enough to train on CPU in real time at this resolution."""

    def __init__(self, n_classes=len(wd.CLASSES)):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(2, 16, 3, padding=1), nn.BatchNorm2d(16), nn.ReLU(), nn.MaxPool2d(2),
            nn.Conv2d(16, 32, 3, padding=1), nn.BatchNorm2d(32), nn.ReLU(), nn.MaxPool2d(2),
            nn.Conv2d(32, 64, 3, padding=1), nn.BatchNorm2d(64), nn.ReLU(), nn.MaxPool2d(2),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(64 * 8 * 8, 128), nn.ReLU(), nn.Dropout(0.3),
            nn.Linear(128, n_classes),
        )

    def forward(self, x):
        return self.classifier(self.features(x))


def _class_weights(labels_idx, n_classes):
    counts = np.bincount(labels_idx, minlength=n_classes).astype(np.float64)
    counts = np.maximum(counts, 1)
    weights = counts.sum() / (n_classes * counts)
    return torch.tensor(weights, dtype=torch.float32)


def _confusion_matrix(y_true, y_pred, n_classes):
    cm = np.zeros((n_classes, n_classes), dtype=int)
    for t, p in zip(y_true, y_pred):
        cm[t, p] += 1
    return cm


def _precision_recall_f1(cm):
    n = cm.shape[0]
    per_class = []
    for c in range(n):
        tp = cm[c, c]
        fp = cm[:, c].sum() - tp
        fn = cm[c, :].sum() - tp
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        per_class.append({"class": wd.CLASSES[c], "precision": precision, "recall": recall,
                           "f1": f1, "support": int(cm[c, :].sum())})
    macro_f1 = float(np.mean([p["f1"] for p in per_class]))
    return per_class, macro_f1


@torch.no_grad()
def _evaluate(model, loader, device):
    model.eval()
    y_true, y_pred = [], []
    for x, y in loader:
        x = x.to(device)
        logits = model(x)
        pred = logits.argmax(dim=1).cpu().numpy()
        y_true.extend(y.numpy().tolist())
        y_pred.extend(pred.tolist())
    cm = _confusion_matrix(y_true, y_pred, len(wd.CLASSES))
    per_class, macro_f1 = _precision_recall_f1(cm)
    accuracy = float(np.mean(np.array(y_true) == np.array(y_pred)))
    return {"confusion_matrix": cm.tolist(), "per_class": per_class, "macro_f1": macro_f1, "accuracy": accuracy}


def train_and_save(epochs=6, batch_size=256, lr=1e-3, seed=13, max_train=None, max_eval=None,
                    max_none_train=25000, log=print, artifact_dir=None):
    """Trains from scratch on the real labeled WM-811K data and writes
    <artifact_dir>/wafer_cnn_{model.pt,metrics.json,samples.json}.
    artifact_dir defaults to ARTIFACT_DIR (the real, served location) --
    smoke tests must pass a throwaway directory instead so they can never
    clobber a real trained model with a 1-epoch/2000-sample toy run.

    max_none_train subsamples ONLY the training split's dominant "none"
    class (real: 117,944 of 138,357 training examples) down to a smaller
    real subset -- combined with the class-weighted loss below, this is a
    standard technique for severe imbalance (the model would otherwise see
    ~1000x more "none" examples than "Near-full" per epoch) and cuts CPU
    training time roughly 3x. Every OTHER class keeps every real training
    example, and val/test are never touched -- they stay the real, honest,
    un-rebalanced distribution so reported metrics reflect real-world class
    frequencies. Set to None to train on the full real training set.

    max_train/max_eval cap the number of examples used (for a fast smoke
    test); leave unset for a real full run."""
    artifact_dir = Path(artifact_dir) if artifact_dir else ARTIFACT_DIR
    model_path = artifact_dir / "wafer_cnn_model.pt"
    metrics_path = artifact_dir / "wafer_cnn_metrics.json"
    samples_path = artifact_dir / "wafer_cnn_samples.json"

    t0 = time.time()
    log("Loading real WM-811K labeled wafers...")
    labeled = wd.load_labeled_wafers()
    train_df, val_df, test_df = wd.stratified_split(labeled, seed=seed)
    if max_none_train:
        none_rows = train_df[train_df.label == "none"]
        if len(none_rows) > max_none_train:
            keep_none = none_rows.sample(n=max_none_train, random_state=seed)
            train_df = pd.concat([train_df[train_df.label != "none"], keep_none]).reset_index(drop=True)
    if max_train:
        train_df = train_df.sample(n=min(max_train, len(train_df)), random_state=seed).reset_index(drop=True)
    if max_eval:
        val_df = val_df.sample(n=min(max_eval, len(val_df)), random_state=seed).reset_index(drop=True)
        test_df = test_df.sample(n=min(max_eval, len(test_df)), random_state=seed).reset_index(drop=True)
    log(f"train={len(train_df)} val={len(val_df)} test={len(test_df)} (loaded in {time.time()-t0:.1f}s)")

    device = torch.device("cpu")
    train_ds, val_ds, test_ds = WaferMapDataset(train_df), WaferMapDataset(val_df), WaferMapDataset(test_df)
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False, num_workers=0)
    test_loader = DataLoader(test_ds, batch_size=batch_size, shuffle=False, num_workers=0)

    model = WaferCNN().to(device)
    weights = _class_weights(train_ds.labels, len(wd.CLASSES)).to(device)
    criterion = nn.CrossEntropyLoss(weight=weights)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)

    history = []
    best_val_f1 = -1.0
    best_state = None
    for epoch in range(1, epochs + 1):
        model.train()
        epoch_t0 = time.time()
        running_loss = 0.0
        n_batches = 0
        for x, y in train_loader:
            x, y = x.to(device), y.to(device)
            optimizer.zero_grad()
            loss = criterion(model(x), y)
            loss.backward()
            optimizer.step()
            running_loss += loss.item()
            n_batches += 1
        val_metrics = _evaluate(model, val_loader, device)
        elapsed = time.time() - epoch_t0
        log(f"epoch {epoch}/{epochs} train_loss={running_loss/n_batches:.4f} "
            f"val_macro_f1={val_metrics['macro_f1']:.4f} val_acc={val_metrics['accuracy']:.4f} ({elapsed:.1f}s)")
        history.append({"epoch": epoch, "train_loss": running_loss / n_batches,
                         "val_macro_f1": val_metrics["macro_f1"], "val_accuracy": val_metrics["accuracy"]})
        if val_metrics["macro_f1"] > best_val_f1:
            best_val_f1 = val_metrics["macro_f1"]
            best_state = {k: v.clone() for k, v in model.state_dict().items()}

    model.load_state_dict(best_state)
    test_metrics = _evaluate(model, test_loader, device)
    log(f"FINAL test_macro_f1={test_metrics['macro_f1']:.4f} test_acc={test_metrics['accuracy']:.4f}")

    artifact_dir.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), model_path)

    metrics = {
        "status": "trained",
        "n_train": len(train_df), "n_val": len(val_df), "n_test": len(test_df),
        "n_labeled_total": len(labeled), "n_unlabeled_total": 811457 - len(labeled),
        "classes": wd.CLASSES,
        "class_distribution": {c: int((labeled.label == c).sum()) for c in wd.CLASSES},
        "train_class_distribution": {c: int((train_df.label == c).sum()) for c in wd.CLASSES},
        "max_none_train": max_none_train,
        "training_history": history,
        "test_confusion_matrix": test_metrics["confusion_matrix"],
        "test_per_class": test_metrics["per_class"],
        "test_macro_f1": test_metrics["macro_f1"],
        "test_accuracy": test_metrics["accuracy"],
        "train_seconds": time.time() - t0,
        "epochs": epochs,
        "wafer_size": wd.WAFER_SIZE,
    }
    metrics_path.write_text(json.dumps(metrics, indent=2))

    _save_sample_gallery(model, test_df, device, samples_path=samples_path)
    log(f"Artifacts written to {artifact_dir} (total {time.time()-t0:.1f}s)")
    return metrics


@torch.no_grad()
def _save_sample_gallery(model, test_df, device, samples_path, n_per_class=3, grid_size=32):
    """A handful of real test-set wafer maps per class, downsized to a small
    grid for the frontend to render directly (no image files needed) with
    true vs. predicted label so a viewer can see real misclassifications,
    not just aggregate numbers."""
    model.eval()
    samples = []
    for cls in wd.CLASSES:
        rows = test_df[test_df.label == cls]
        if len(rows) == 0:
            continue
        rows = rows.sample(n=min(n_per_class, len(rows)), random_state=1)
        for _, row in rows.iterrows():
            enc = wd.encode_wafer_map(row.waferMap, size=grid_size)
            model_input = wd.encode_wafer_map(row.waferMap, size=wd.WAFER_SIZE)
            logits = model(torch.from_numpy(model_input).unsqueeze(0).to(device))
            pred_idx = int(logits.argmax(dim=1).item())
            grid = np.zeros((grid_size, grid_size), dtype=int)
            grid[enc[0] >= 1] = 1
            grid[enc[1] >= 1] = 2
            samples.append({
                "true_label": cls,
                "predicted_label": wd.CLASSES[pred_idx],
                "correct": wd.CLASSES[pred_idx] == cls,
                "grid": grid.tolist(),
            })
    samples_path.write_text(json.dumps(samples))


def load_artifacts():
    """What the live API calls -- fast (loads a small JSON), never trains.
    Real status reporting if training hasn't been run on this machine yet,
    matching the license_required pattern used elsewhere in this app."""
    if not METRICS_PATH.exists():
        return {"status": "not_trained", "message": "Run scripts/train_wafer_cnn.py first (needs data/wm811k/LSWMD.pkl)."}
    metrics = json.loads(METRICS_PATH.read_text())
    if SAMPLES_PATH.exists():
        metrics["sample_gallery"] = json.loads(SAMPLES_PATH.read_text())
    return metrics
