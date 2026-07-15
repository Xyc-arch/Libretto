#!/usr/bin/env python3
"""Reproducibility tests for the pkg-native gaptask pipeline: the balanced case builder, the conditioned
reprise gate + its calibrator, and the metrics-only audition / loop-benefit drivers. Everything here runs
WITHOUT an agent (deterministic from the frozen core)."""
import json
import os

import pytest

import libretto
from libretto.tasks.gaptask import build_cases as bc
from libretto.tasks.gaptask import refine_loop as grl
from libretto.tasks.gaptask.loop import loop_benefit as lb
from libretto.tasks.gaptask.loop import audition as aud

DATA = libretto.data_root()
REPO = DATA.parents[1]
CANON_CASES = REPO / "paper_data/gaptask_v3/cases"
CANON_STATE = REPO / "gaptask_loop/state"


# ── conditioned reprise gate ────────────────────────────────────────────────────────────────────────
def test_reprise_threshold_accessor():
    shipped = json.loads((DATA / "gaptask_region_reprise_p75.json").read_text())
    for t, v in shipped.items():
        assert grl.region_reprise_threshold(t) == v
    # unknown / None gap-type falls back to the region default, not a flat 0.30
    assert grl.region_reprise_threshold("no_such_type") == grl.REPRISE_FALLBACK
    assert grl.region_reprise_threshold(None) == grl.REPRISE_FALLBACK
    assert all(0.5 < v < 0.95 for v in shipped.values()), "reprise p75 should sit in the real-music band"


def test_reprise_gate_is_reproducible(tmp_path):
    # the shipped reprise gate must be exactly regenerable from the frozen core (full-corpus calibration, ~90s)
    if os.environ.get("GAPTASK_SLOW_TESTS") != "1":
        pytest.skip("slow full-corpus calibration; set GAPTASK_SLOW_TESTS=1 to run")
    shipped = json.loads((DATA / "gaptask_region_reprise_p75.json").read_text())
    regen = grl.calibrate_region_reprise(out_path=str(tmp_path / "r.json"))
    assert dict(sorted(regen.items())) == dict(sorted(shipped.items())), \
        "calibrate_region_reprise() no longer reproduces the shipped gaptask reprise gate"


# ── balanced case builder ───────────────────────────────────────────────────────────────────────────
def test_build_cases_is_balanced_and_deterministic(tmp_path):
    a = bc.build_cases(seed=1, out=str(tmp_path / "a"))
    b = bc.build_cases(seed=1, out=str(tmp_path / "b"))
    assert a == b, "build_cases must be deterministic for a fixed seed"
    for var in bc.VARIANTS:
        gs = sorted(c["genre"] for c in a.values() if c["type"] == var)
        assert gs == sorted(bc.GENRES), f"{var} batch is not genre-balanced (one song per genre)"


def test_build_cases_reproduces_shipped_canonical(tmp_path):
    if not (CANON_CASES / "cases.json").exists():
        pytest.skip("canonical cases not present")
    shipped = json.loads((CANON_CASES / "cases.json").read_text())
    bc.build_cases(seed=1, out=str(tmp_path / "c"))
    # compare the written case set (serialized: tuples -> lists, same as the shipped file)
    regen = json.loads((tmp_path / "c" / "cases.json").read_text())
    assert regen == shipped, "build_cases(seed=1) no longer reproduces the shipped canonical case set"


# ── metrics-only drivers (no agent) ─────────────────────────────────────────────────────────────────
def test_loop_benefit_runs_on_canonical():
    if not (CANON_STATE).exists():
        pytest.skip("canonical batch state not present")
    summary, rows = lb.loop_benefit(CANON_CASES, CANON_STATE)
    assert summary["n"] == len(rows) > 0
    assert summary["gate_loop_best"] >= summary["gate_single_shot"], "loop must not reduce gate-pass"


def test_audition_repick_is_deterministic(tmp_path):
    if not (CANON_STATE).exists():
        pytest.skip("canonical batch state not present")
    # metrics-only (SOUNDFONT unset in tmp env is fine — render degrades to skip, index still written)
    idx = aud.audition(CANON_CASES, CANON_STATE, str(tmp_path / "listen"))
    assert idx["n_cases"] > 0
    assert idx["saved_copy_pass"] + idx["flagged_not_saved"] == idx["n_cases"]
    # every saved row carries a genre-labelled gen filename
    for r in idx["rows"]:
        if r["copy_pass"]:
            assert r["gen_mp3"] == f"{r['genre']}__{r['case']}__gen.mp3"


if __name__ == "__main__":
    test_reprise_threshold_accessor()
    import tempfile
    import pathlib
    test_build_cases_is_balanced_and_deterministic(pathlib.Path(tempfile.mkdtemp()))
    print("gaptask reproduce (fast) tests passed")
