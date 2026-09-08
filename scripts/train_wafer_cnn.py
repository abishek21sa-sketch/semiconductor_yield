"""
One-time training run for the WM-811K wafer defect CNN (pipeline/wafer_cnn.py).
Not run automatically at server startup -- takes real minutes on CPU. Run it
once after placing data/wm811k/LSWMD.pkl, then the API loads its output
(data/wm811k/wafer_cnn_model.pt + wafer_cnn_metrics.json) instantly.

Usage:
    python scripts/train_wafer_cnn.py                  # full real run
    python scripts/train_wafer_cnn.py --smoke-test      # fast correctness check on a small subset
"""
import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import wafer_cnn  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=6)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--smoke-test", action="store_true", help="tiny subset, 1 epoch, just to check the pipeline runs end to end")
    args = parser.parse_args()

    if args.smoke_test:
        # Writes to a throwaway temp dir, never ARTIFACT_DIR -- a 1-epoch/
        # 2000-sample toy run must never overwrite a real trained model.
        with tempfile.TemporaryDirectory() as tmp:
            wafer_cnn.train_and_save(epochs=1, batch_size=64, max_train=2000, max_eval=500, artifact_dir=tmp)
    else:
        wafer_cnn.train_and_save(epochs=args.epochs, batch_size=args.batch_size)
