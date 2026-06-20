#!/usr/bin/env python3
"""Tests for newgen's ADAPTIVE calibrated criteria + MANDATORY retrieval."""
import json
import pytest

import libretto
from libretto.tasks.newgen import calibrate as cal
from libretto.tasks.newgen import retrieval as R

DATA = libretto.data_root()
GENRES = ["classical", "core_pop_rock", "electronic_dance", "film_score",
          "folk_country", "funk_soul_rnb", "jazz", "latin_reggae_world"]


def test_calibration_cached_and_sane():
    c = cal.calibration()
    for g in GENRES:
        assert g in c["genres"], f"{g} missing from calibration"
        b = cal.c1_budget(g); f = cal.fit_threshold(g); cp = cal.copy_threshold(g)
        assert 3 <= b <= 6 and 3 <= f <= 6
        assert cal.COPY_FLOOR <= cp <= cal.COPY_CAP
    # adaptive: a naturally-varied genre gets a looser C1 budget than a tight one
    assert cal.c1_budget("jazz") >= cal.c1_budget("core_pop_rock")
    # unknown / brief -> conservative floors
    assert cal.c1_budget(None) == 3 and cal.fit_threshold(None) == 3 and cal.copy_threshold(None) == cal.COPY_FLOOR


def test_copy_threshold_adaptive_with_headroom():
    """Copy gate is per-genre and never stricter than 0.30; idiom carries 20% headroom above the real ceiling."""
    c = cal.calibration()
    for g in GENRES:
        d = c["genres"][g]
        assert cal.copy_threshold(g) >= cal.COPY_FLOOR                       # never stricter than the standard
        # the threshold reflects the genre's real copy ceiling x tolerance (when above the 0.30 floor)
        expect = round(min(cal.COPY_CAP, max(cal.COPY_FLOOR, d["real_copy_ceiling"] * cal.COPY_TOLERANCE)), 2)
        assert cal.copy_threshold(g) == expect


def test_calibration_admits_more_real_songs_than_fixed_gate():
    """The whole point: the old fixed fit>=6 rejected ~80% of real songs; the calibrated floor must be lower."""
    for g in GENRES:
        assert cal.fit_threshold(g) <= 6
    assert cal.fit_threshold("latin_reggae_world") < 6


def test_retrieval_is_mandatory_and_grounded():
    r = R.build_retrieval("latin_reggae_world")
    assert r["concept_ids"] and r["exemplar_ids"]
    assert "EXAMPLE:" in r["text"] and "COMPOSE:" in r["text"]      # real corpus example + generative move
    assert "STYLE REFERENCE" in r["text"]                          # exemplar excerpts present
    # every mapped genre resolves to at least one real concept entry
    for g in GENRES:
        ids, block = R.concepts_block(g)
        assert ids and block.strip()


def test_retrieval_excludes_held_out_song():
    target = R.prototypical_songs("latin_reggae_world", k=1)[0]
    r = R.build_retrieval("latin_reggae_world", exclude={target})
    assert target not in r["exemplar_ids"]


def test_unmapped_genre_raises():
    with pytest.raises(ValueError):
        R.concepts_block("polka_nonexistent")


if __name__ == "__main__":
    test_calibration_cached_and_sane()
    test_calibration_admits_more_real_songs_than_fixed_gate()
    test_retrieval_is_mandatory_and_grounded()
    test_retrieval_excludes_held_out_song()
    print("all newgen-adaptive tests passed")
