#!/usr/bin/env python3
"""Tests for the morph generation loop wiring (no agent): the prompt carries the per-segment trajectory + both
objectives, and morph_feedback targets exactly the lenses that scored low."""
import json

import libretto
from libretto.tasks.morph import build_cases as mbc
from libretto.tasks.morph.loop import batch


def _case():
    cases = mbc.build_cases(seed=0, out=str(libretto.data_root().parent / "_morph_test_cases"))
    return next(iter(cases.values()))


def test_prompt_has_trajectory_and_objectives():
    c = _case()
    p = batch.build_prompt(c)
    assert c["genreA"] in p and c["genreB"] in p
    assert "GRADUAL" in p and "GENRE SHIFT" in p
    assert "morph_axis_trajectory_percentiles" in p
    # the trajectory JSON should list one series per morph axis with S points
    ctx = json.loads(p.split("```json", 1)[1].split("```", 1)[0])
    traj = ctx["morph_axis_trajectory_percentiles"]
    assert traj and all(len(v) == c["S"] for v in traj.values())


def test_feedback_targets_low_lenses_only():
    c = _case()
    # a result that fails everything -> feedback should mention anchors, monotonic, even, both genre dirs, crossover
    bad = dict(S=c["S"], genuinely_new=False,
               graduality=dict(score=0.2, progress=[0.5, 0.3, 0.45, 0.6, 0.55, 0.7][:c["S"]],
                               anchored=False, backtracks=2, max_jolt=3.0),
               genre_shift=dict(same_genre=False, source_genre=c["genreA"], target_genre=c["genreB"],
                                target_rise_spearman=0.1, source_fall_spearman=-0.1, crossover_seg=None))
    fb = " ".join(batch.morph_feedback(bad))
    for token in ("ANCHORS", "MONOTONIC", "EVEN STEPS", "GENRE (target)", "GENRE (source)", "CROSSOVER", "NOVELTY"):
        assert token in fb, f"feedback missing {token}"
    # a perfect result -> no corrections
    good = dict(S=c["S"], genuinely_new=True,
                graduality=dict(score=0.95, progress=[i / (c["S"] - 1) for i in range(c["S"])],
                                anchored=True, backtracks=0, max_jolt=1.1),
                genre_shift=dict(same_genre=False, source_genre=c["genreA"], target_genre=c["genreB"],
                                 target_rise_spearman=1.0, source_fall_spearman=-1.0, crossover_seg=c["S"] // 2))
    assert batch.morph_feedback(good) == []


if __name__ == "__main__":
    test_prompt_has_trajectory_and_objectives()
    test_feedback_targets_low_lenses_only()
    print("morph loop wiring tests passed")


def test_loop_benefit_runs_if_state_present():
    import libretto
    from libretto.tasks.morph.loop import loop_benefit as lbm
    REPO = libretto.data_root().parents[1]
    cases = REPO / "compositions/morph/cases"
    state = REPO / "morph_loop/state"
    if not (cases / "cases.json").exists() or not state.exists():
        import pytest; pytest.skip("no morph batch state present")
    s, rows = lbm.loop_benefit(cases, state)
    assert s["n"] == len(rows) > 0
    assert s["score_loop_best"] >= s["score_single_shot"], "loop must not reduce mean morph_score"
