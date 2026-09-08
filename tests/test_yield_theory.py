import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import yield_model


def test_poisson_yield_known_value():
    # Y = exp(-D0*A); at D0*A = 1, Y = e^-1.
    assert math.isclose(yield_model.poisson_yield(1.0, 1.0), math.exp(-1), rel_tol=1e-9)


def test_yield_is_one_at_zero_defect_density():
    assert yield_model.poisson_yield(0.0, 1.0) == 1.0
    assert yield_model.murphy_yield(0.0, 1.0) == 1.0
    assert yield_model.negative_binomial_yield(0.0, 1.0) == 1.0


def test_yield_decreases_with_die_area():
    areas = [0.5, 1.0, 2.0, 4.0]
    for fn in (yield_model.poisson_yield, yield_model.murphy_yield, yield_model.negative_binomial_yield):
        ys = [fn(0.4, a) for a in areas]
        assert ys == sorted(ys, reverse=True)


def test_murphy_yield_exceeds_poisson_for_same_defect_load():
    # Murphy's model accounts for defect clustering and predicts a higher
    # yield than the naive uniform-defect Poisson model at the same D0*A.
    for d0a in [(0.3, 1.0), (0.5, 2.0), (1.0, 1.0)]:
        d0, a = d0a
        assert yield_model.murphy_yield(d0, a) >= yield_model.poisson_yield(d0, a)


def test_negative_binomial_converges_to_poisson_as_alpha_grows():
    d0, a = 0.6, 1.5
    poisson = yield_model.poisson_yield(d0, a)
    nbd_large_alpha = yield_model.negative_binomial_yield(d0, a, cluster_alpha=10_000)
    assert math.isclose(nbd_large_alpha, poisson, rel_tol=1e-3)


def test_yield_model_curve_shape():
    curve = yield_model.yield_model_curve([0.5, 1.0, 1.5], defect_density_per_cm2=0.4)
    assert len(curve) == 3
    for row in curve:
        assert 0.0 <= row["poisson"] <= 1.0
        assert 0.0 <= row["murphy"] <= 1.0
        assert 0.0 <= row["negative_binomial"] <= 1.0
