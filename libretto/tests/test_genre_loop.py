"""Tooling test for the self-evolving loop's genre-ADAPTIVE per-round engine (not a frozen-core guard).

Run: `python -m pytest libretto/tests/test_genre_loop.py` or `python libretto/tests/test_genre_loop.py`.
"""
import libretto
from libretto.core import genre_band_check as gbc

REF = (libretto.data_root().parent / "tasks" / "genre_loop" / "refdata" / "jazzloop" / "r5.txt")


def test_all_genres_are_valid_targets():
    gs = gbc.genres()
    assert len(gs) == 9 and "jazz" in gs and "classical" in gs


def test_engine_is_genre_adaptive():
    """Same piece, different genre target -> different verdict (proves it is not genre-fixed)."""
    jazz_oob = {a for a, *_ in gbc.check(str(REF), genre="jazz")[0] if a in gbc.SPLIT}
    classical_oob = {a for a, *_ in gbc.check(str(REF), genre="classical")[0] if a in gbc.SPLIT}
    # the converged jazz piece is fully in-band for jazz, but off-band on >=1 split axis for classical
    assert jazz_oob == set()
    assert "rhy_triplet_share" in classical_oob


def test_degenerate_band_widens_not_hardcoded():
    """jazz distinct_pc band is pinned at 12 (p25=p75); the value 12 must read in-band via [p5,p95]."""
    lo, p50, hi = gbc.genre_band("har_distinct_pc", "jazz")
    assert lo < hi and lo <= 12.0 <= hi   # widened to the genre's data-driven soft band, no hack


def test_global_mode_runs():
    oob, ext, nb = gbc.check(str(REF), genre=None)
    assert nb > 0 and isinstance(oob, list)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print("PASS", name)
    print("all genre-loop tooling tests passed")
