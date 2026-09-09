"""
One-time training run for the WM-811K wafer defect CNN (pipeline/wafer_cnn.py)
plus its hand-engineered-feature baseline (pipeline/wafer_baseline.py). Not
run automatically at server startup -- takes real minutes on CPU. Run it
once after placing data/wm811k/LSWMD.pkl, then the API loads the outputs
(data/wm811k/wafer_cnn_*.{pt,json}, wafer_baseline_metrics.json) instantly.

Usage:
    python scripts/train_wafer_cnn.py                  # full real run (CNN + baseline)
    python scripts/train_wafer_cnn.py --smoke-test      # fast correctness check on a small subset
    python scripts/train_wafer_cnn.py --cnn-only        # skip the baseline
    python scripts/train_wafer_cnn.py --baseline-only   # skip the CNN
    python scripts/train_wafer_cnn.py --ab-test         # controlled augment on/off comparison,
                                                         # same seed both runs, writes to temp dirs
"""
import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import wafer_baseline, wafer_cnn  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=6)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--smoke-test", action="store_true", help="tiny subset, 1 epoch, just to check the pipeline runs end to end")
    parser.add_argument("--cnn-only", action="store_true")
    parser.add_argument("--baseline-only", action="store_true")
    parser.add_argument("--ab-test", action="store_true",
                         help="controlled augment=True vs augment=False comparison, same seed, "
                              "same epoch count -- a real answer to whether augmentation helps, "
                              "not a comparison confounded by unseeded random init")
    parser.add_argument("--ab-epochs", type=int, default=6, help="epoch count for --ab-test (both arms)")
    args = parser.parse_args()

    if args.ab_test:
        # augment=False writes to the REAL artifact dir -- it's the exact
        # config we ship, so this run does double duty as both the A/B
        # baseline arm and the real trained model, instead of a third
        # redundant full run. augment=True is comparison-only, temp dir.
        results = {}
        print("\n=== A/B run: augment=False (also the real shipped model) ===")
        results[False] = wafer_cnn.train_and_save(epochs=args.ab_epochs, seed=13, augment=False)
        if not args.baseline_only:
            wafer_baseline.train_and_evaluate()
        with tempfile.TemporaryDirectory() as tmp:
            print("\n=== A/B run: augment=True (comparison only) ===")
            results[True] = wafer_cnn.train_and_save(epochs=args.ab_epochs, seed=13, augment=True, artifact_dir=tmp)
        print("\n=== A/B RESULT (same seed=13, same epochs, controlled) ===")
        for augment, r in results.items():
            print(f"augment={augment}: test_macro_f1={r['test_macro_f1']:.4f} test_accuracy={r['test_accuracy']:.4f}")
        delta = results[True]["test_macro_f1"] - results[False]["test_macro_f1"]
        print(f"delta (augment=True minus augment=False): {delta:+.4f} macro-F1")
    elif args.smoke_test:
        # Writes to a throwaway temp dir, never the real artifact paths --
        # a toy run must never overwrite a real trained model.
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            if not args.baseline_only:
                wafer_cnn.train_and_save(epochs=1, batch_size=64, max_train=2000, max_eval=500, artifact_dir=tmp)
            if not args.cnn_only:
                wafer_baseline.train_and_evaluate(max_none_train=1000, metrics_path=tmp_path / "baseline_smoke.json")
    else:
        if not args.baseline_only:
            wafer_cnn.train_and_save(epochs=args.epochs, batch_size=args.batch_size)
        if not args.cnn_only:
            wafer_baseline.train_and_evaluate()
