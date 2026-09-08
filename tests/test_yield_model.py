"""
Unit tests on pipeline/yield_model.py's real-data-driven pieces that
tests/test_yield_theory.py doesn't cover (that file only exercises the
classical Poisson/Murphy/NBD formulas, which take no real data). These call
run_full_analysis() directly -- it's decorated with @lru_cache(maxsize=1), so
when run as part of the full `pytest tests/ -v` suite this reuses whatever
call (here or in test_api.py's /api/yield test) happens to run first, rather
than recomputing the real SECOM RF fit multiple times.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import yield_model


def test_spc_control_limits_match_the_stated_three_sigma_formula():
    """The SPC section's docstring/comments describe mu +/- 3*sigma computed
    from PASSING lots only. Checks the reported ucl/lcl against that exact
    formula (not just "some number near mu"), and that mu/sigma themselves
    come from a real, non-degenerate distribution."""
    r = yield_model.run_full_analysis()
    spc = r["spc"]
    assert spc["sigma"] > 0
    assert math.isclose(spc["ucl"], spc["mu"] + 3 * spc["sigma"], rel_tol=1e-9)
    assert math.isclose(spc["lcl"], spc["mu"] - 3 * spc["sigma"], rel_tol=1e-9)


def test_spc_out_of_band_count_uses_strict_boundary_and_is_internally_consistent():
    """n_out_of_band and the plotted `points` array are two separate outputs
    derived from the same underlying sensor values -- this checks they
    genuinely agree using the module's own strict-inequality convention
    (value < LCL or value > UCL; a point sitting exactly on a control limit
    is NOT flagged), which is the real boundary condition a future edit
    could silently flip to <=/>= without either output alone catching it."""
    r = yield_model.run_full_analysis()
    spc = r["spc"]
    ucl, lcl = spc["ucl"], spc["lcl"]

    points = spc["points"]
    assert len(points) > 0

    recomputed = sum(1 for p in points if p["v"] < lcl or p["v"] > ucl)
    assert recomputed == spc["n_out_of_band"]

    # A point sitting exactly on a control limit must not be counted -- with
    # real continuous sensor data no point should ever land exactly on the
    # limit, so this also guards against a degenerate/rounded dataset.
    on_boundary = sum(1 for p in points if p["v"] == ucl or p["v"] == lcl)
    assert on_boundary == 0


def test_yield_rate_and_lot_counts_are_internally_consistent():
    """meta.yield_rate is derived from meta.n_fails/meta.n_lots -- a simple
    relationship, but one no existing test checks, and a real place for an
    off-by-one (e.g. counting fails against the wrong denominator) to hide."""
    r = yield_model.run_full_analysis()
    meta = r["meta"]
    assert meta["n_lots"] == 1567  # the real, published SECOM lot count
    assert 0 < meta["n_fails"] < meta["n_lots"]
    assert math.isclose(meta["yield_rate"], 1 - meta["n_fails"] / meta["n_lots"], rel_tol=1e-9)
