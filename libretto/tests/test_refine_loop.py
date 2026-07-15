#!/usr/bin/env python3
"""Tests for the refinement-loop pipeline: axis_feedback completeness, musician-readable dosage feedback,
and a deterministic end-to-end RefinementLoop run with the EchoGenerator (no LLM)."""
import json
import libretto
from libretto.core import axis_feedback as afb
from libretto.generation.interface import EchoGenerator
from libretto.tasks.newgen import refine_loop as nrl
from libretto.tasks.gaptask import refine_loop as grl

DATA = libretto.data_root()
AXES = json.loads((DATA / "corpus_distribution.json").read_text())["axes_order"]


def test_axis_feedback_covers_all_axes():
    for a in AXES:
        assert a in afb.AXIS_DEF, f"axis {a} missing a definition"
        up = afb.explain(a, "LOW"); down = afb.explain(a, "HIGH")
        assert up and down and up != down, f"{a} raise/lower lines must differ and be non-empty"
        assert "raise" in up and "lower" in down, f"{a} should state the direction to move"


def test_explain_is_grounded_not_prescriptive():
    s = afb.explain("tex_mean_simultaneity", "LOW", pct=3)
    assert "texture fullness" in s and "3th pct" in s and "raise" in s
    assert "you choose how" in s  # non-prescriptive: model decides the musical realisation


def test_dosage_feedback_grounded():
    # one out-of-band axis -> feedback states the trait + where it sits + direction, never the raw metric id
    fit = {"c2_pass": True, "bars": 96, "c1_extremes": [], "copy_pass": True, "copy_risk": 0.1,
           "oob": [("tex_mean_simultaneity", 3.0, "LOW")], "genre_fit_out": []}
    fb = nrl.dosage_feedback(fit)
    assert any("texture fullness" in line and "raise" in line for line in fb)
    assert all("tex_mean_simultaneity" not in line for line in fb)  # raw metric id not leaked


def test_refinement_loop_runs_with_echo(tmp_path):
    # EchoGenerator returns context['seed_grammar'] verbatim each round -> deterministic, no LLM.
    seed = (DATA / "grammar" / "song_0001.txt").read_text(encoding="utf-8")
    loop = nrl.RefinementLoop(EchoGenerator(), max_iter=2)
    best, rounds = loop.run("BASE PROMPT", genre=None, context={"seed_grammar": seed},
                            workdir=str(tmp_path), label="t")
    assert 1 <= len(rounds) <= 2
    assert best is not None and "score" in best and "feedback" in best
    assert (tmp_path / "t_r1.txt").exists()


def test_gaptask_region_budget_accessor():
    # shipped data drives the accessor; unknown/None genre falls back to the region default (not 3)
    shipped = json.loads((DATA / "gaptask_region_c1_budget.json").read_text())
    for g, b in shipped.items():
        assert grl.region_c1_budget(g) == b
    assert grl.region_c1_budget("no_such_genre") == grl.REGION_BUDGET_DEFAULT
    assert grl.region_c1_budget(None) == grl.REGION_BUDGET_DEFAULT


def test_gaptask_region_budget_is_reproducible(tmp_path):
    # the shipped budget must be exactly regenerable from the frozen core via the pkg calibrator
    shipped = json.loads((DATA / "gaptask_region_c1_budget.json").read_text())
    regen = grl.calibrate_region_budgets(out_path=str(tmp_path / "b.json"))
    assert dict(sorted(regen.items())) == dict(sorted(shipped.items())), \
        "calibrate_region_budgets() no longer reproduces the shipped gaptask region budget"


if __name__ == "__main__":
    test_axis_feedback_covers_all_axes()
    test_explain_is_grounded_not_prescriptive()
    test_dosage_feedback_grounded()
    import tempfile, pathlib
    test_refinement_loop_runs_with_echo(pathlib.Path(tempfile.mkdtemp()))
    print("all refine_loop tests passed")
