#!/usr/bin/env python3
"""Tests for the morph metric: GRADUALITY (axis-trajectory monotonicity + even steps + anchoring) and the
GENRE-SHIFT classifier lens. Graduality is tested on synthetic fingerprint trajectories (no classifier, fast);
the full metric + genre-shift get a smoke test on a real morph if present."""
import numpy as np
import pytest

import libretto
from libretto.tasks.morph import morph_metric as mm
from libretto.tasks.morph import build_cases as mbc

REPO = libretto.data_root().parents[1]
N = len(mm.AXES)


def _fps(fpA, fpB, alphas):
    return [fpA + a * (fpB - fpA) for a in alphas]


def test_graduality_perfect_linear_morph():
    fpA = np.zeros(N); fpB = np.zeros(N)
    for i in range(5):
        fpB[i] = 100.0                                   # 5 morph axes, differ by 100 >> MORPH_MIN_DIFF
    segs = _fps(fpA, fpB, [0, .2, .4, .6, .8, 1.0])      # perfectly even A->B glide
    g = mm.graduality(segs, fpA, fpB)
    assert g["monotonic_spearman"] == pytest.approx(1.0)
    assert g["span"] > 0.9 and g["anchored"] and g["backtracks"] == 0
    assert g["evenness"] > 0.9                           # even steps -> gradual
    assert g["score"] > 0.9


def test_graduality_flags_abrupt_and_backtracking():
    fpA = np.zeros(N); fpB = np.zeros(N)
    for i in range(5):
        fpB[i] = 100.0
    # abrupt: sits at A then jumps to B (a splice, not a glide)
    abrupt = mm.graduality(_fps(fpA, fpB, [0, 0, 0, 1, 1, 1]), fpA, fpB)
    assert abrupt["max_jolt"] > 2.0 and abrupt["evenness"] < 0.6
    assert abrupt["score"] < 0.9
    # backtracking trajectory is caught
    back = mm.graduality(_fps(fpA, fpB, [0, .5, .2, .6, .3, 1.0]), fpA, fpB)
    assert back["backtracks"] >= 1


def test_graduality_static_has_no_span():
    fpA = np.zeros(N); fpB = np.zeros(N); fpB[:5] = 100.0
    g = mm.graduality(_fps(fpA, fpB, [0, 0, 0, 0, 0, 0]), fpA, fpB)   # never leaves A
    assert g["span"] == pytest.approx(0.0) and g["score"] < 0.5


def test_genre_shift_keys_and_range():
    # a synthetic 6-segment set of real corpus fingerprints -> classifier returns a well-formed shift dict
    import json
    fps = json.loads((libretto.data_root() / "corpus_fps.json").read_text())
    some = [np.array(v, float) for v in list(fps.values())[:6]]
    s = mm.genre_shift(some, "jazz", "metal")
    for k in ("p_source", "p_target", "reads_as", "target_rise_spearman", "source_fall_spearman", "score"):
        assert k in s
    assert 0.0 <= s["score"] <= 1.0 and len(s["p_target"]) == 6


def test_morph_metric_smoke_on_real_morph():
    morph = REPO / "compositions/morph/morph_song_0184_song_0149.txt"
    if not morph.exists():
        pytest.skip("no real morph present")
    r = mm.morph_metric(str(morph), "song_0184", "song_0149", 6)
    assert 0.0 <= r["morph_score"] <= 1.0
    assert set(("graduality", "genre_shift", "genuinely_new")) <= set(r)
    assert r["graduality"]["monotonic_spearman"] <= 1.0


def test_build_cases_balanced_cross_genre_and_deterministic(tmp_path):
    a = mbc.build_cases(seed=0, out=str(tmp_path / "a"))
    b = mbc.build_cases(seed=0, out=str(tmp_path / "b"))
    assert a == b, "morph build_cases must be deterministic for a fixed seed"
    assert len(a) == len(mbc.GENRES)
    # every genre is source once and target once, and every pair is cross-genre
    from collections import Counter
    src = Counter(c["genreA"] for c in a.values()); tgt = Counter(c["genreB"] for c in a.values())
    assert all(src[g] == 1 and tgt[g] == 1 for g in mbc.GENRES)
    assert all(c["genreA"] != c["genreB"] for c in a.values())
    # case schema carries the morph plan
    c0 = next(iter(a.values()))
    for k in ("fpA", "fpB", "targets", "morph_axes", "keyA", "keyB"):
        assert k in c0
    assert len(c0["targets"]) == c0["S"] and len(c0["fpA"]) == N


def test_exemplars_read_as_their_genre():
    # exemplar selection (max classifier confidence) => endpoints are unambiguous genre anchors
    clf, genres = mm._classifier()
    ex = mbc.genre_exemplars(0)
    ok = sum(genres[int(np.argmax(clf.predict_proba([mbc.CFP[sid]])[0]))] == g for g, sid in ex.items())
    assert ok >= 10, f"only {ok}/11 exemplars read as their own genre"


if __name__ == "__main__":
    test_graduality_perfect_linear_morph()
    test_graduality_flags_abrupt_and_backtracking()
    test_graduality_static_has_no_span()
    print("morph graduality tests passed")
