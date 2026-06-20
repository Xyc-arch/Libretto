#!/usr/bin/env python3
"""Tests for the education task: kb_theory retrieval, scale logic, challenge detectors, and copy control."""
import tempfile
from pathlib import Path

import libretto
from libretto.tasks.education import retrieval as R, setup as S, measure as M


def test_kb_theory_loads_and_every_entry_has_grammar():
    e = R.entries()
    assert len(e) >= 120
    for cid, v in e.items():
        assert v["grammar"].lstrip().startswith("KEY:") and "VOICES: Piano" in v["grammar"]


def test_scale_pcs():
    _, pcs, mode = M.scale_pcs("A harmonic minor")
    assert pcs == {9, 11, 0, 2, 4, 5, 8} and mode == "harmonic minor"
    _, cpcs, _ = M.scale_pcs("C major")
    assert cpcs == {0, 2, 4, 5, 7, 9, 11}


def test_build_context_and_shown_grammars():
    ctx = R.build_context(["TR-SYNCOPATION", "TS-HARMONIC-MINOR"], with_exemplar=True)
    assert ctx["concept_ids"] == ["TR-SYNCOPATION", "TS-HARMONIC-MINOR"]
    assert len(ctx["shown_grammars"]) >= 2 and "kb_theory" in ctx["text"].lower() or "REQUIRED" in ctx["text"]


def test_copy_control_catches_verbatim_echo(tmp_path):
    """Feeding the kb example back verbatim must FAIL novelty (copy_vs_shown ~ 1.0)."""
    ex = R.concept("TR-SYNCOPATION")["grammar"]
    p = tmp_path / "echo.txt"; p.write_text(ex + "\n")
    ctx = R.build_context(["TR-SYNCOPATION"], with_exemplar=False)
    case = {"key": "C major", "concept_ids": ["TR-SYNCOPATION"], "shown_grammars": ctx["shown_grammars"]}
    r = M.measure(p, case)
    assert r["copy_vs_shown"] > 0.9 and r["novel"] is False and r["verdict"] is False


def test_challenge_detectors_on_kb_examples():
    # the kb examples are designed to demonstrate their own concept -> the detector should fire
    for cid, key in [("TR-SYNCOPATION", "C major"), ("TM-LEAP", "C major")]:
        g = R.concept(cid)["grammar"]
        d = Path(tempfile.mkdtemp()) / "x.txt"; d.write_text(g + "\n")
        from libretto.core import Song
        lbl, ok, detail = M.detect_challenge(cid, Song(d).events, g)
        assert ok is True, f"{cid}: {lbl}"


if __name__ == "__main__":
    test_kb_theory_loads_and_every_entry_has_grammar()
    test_scale_pcs()
    test_build_context_and_shown_grammars()
    import pathlib, tempfile
    test_copy_control_catches_verbatim_echo(pathlib.Path(tempfile.mkdtemp()))
    test_challenge_detectors_on_kb_examples()
    print("all education tests passed")


# ---- difficulty auto-scaler, requirement checks, and the refine loop ----
def test_autoscale_by_level():
    from libretto.tasks.education import curriculum as C
    for lvl in ("beginner", "intermediate", "advanced"):
        ids = C.autoscale(lvl, n=4)
        assert len(ids) == 4 and len(set(ids)) == 4
        # every picked id is a real kb_theory concept
        for cid in ids:
            assert cid in R.entries()
    # dimension focus is honoured
    ids = C.autoscale("intermediate", ["rhythm", "chord"], n=4)
    assert any(i.startswith("TR-") for i in ids) and any(i.startswith("TC-") for i in ids)


def test_requirement_checks_meter_tempo_chords(tmp_path):
    from libretto.core import Song
    g = ("KEY: D minor | METER: 3/4 | TEMPO: 138 | GRID: 16th | BARS: 3\nVOICES: Piano\n"
         "@1 [Dm]\n  Piano: D4+F4+A4@1>4 A4@5>2 F4@7>2 D4@9>4\n"
         "@2 [Gm]\n  Piano: G3+Bb3+D4@1>4 D4@5>2 Bb3@7>2 G3@9>4\n"
         "@3 [Dm]\n  Piano: D4+F4+A4@1>4 F4@5>2 A4@7>2 D5@9>4\n")
    p = tmp_path / "x.txt"; p.write_text(g)
    case = {"key": "D minor", "concept_ids": [], "shown_grammars": [],
            "meter": "3/4", "tempo_bpm": 138, "tempo_range": [120, 156],
            "require_chords": ["Dm", "Gm"], "dominant_chord": "Dm",
            "rhythm_feel_target": {"feel": "fast", "max_median_dur": 1.0, "min_onsets_per_bar": 3.0}}
    rep = M.measure(p, case)
    by = {c["check"].split(" ")[0]: c["pass"] for c in rep["requirement_checks"]}
    labels = [c["check"] for c in rep["requirement_checks"]]
    assert any("3/4 == 3/4" in l for l in labels)
    assert rep["requirement_pass"] is True   # meter, tempo, chords, dominant Dm, fast feel all hold


class _BadGen:
    def generate(self, prompt, ctx):  # wrong meter -> requirement fails every round
        return ("KEY: C major | METER: 4/4 | TEMPO: 90 | GRID: 16th | BARS: 2\nVOICES: Piano\n"
                "@1 [C]\n  Piano: C4@1>4 E4@5>4 G4@9>4 C5@13>4\n"
                "@2 [C]\n  Piano: C4@1>4 E4@5>4 G4@9>4 C5@13>4\n")


def test_refine_loop_runs_and_picks_best(tmp_path):
    from libretto.tasks.education.refine_loop import RefinementLoop
    spec = {"level": "beginner", "key": "C major", "meter": "3/4", "concept_ids": ["TR-QUARTER-NOTE"],
            "title": "t", "with_exemplar": False}
    best, rounds = RefinementLoop(_BadGen(), max_iter=2).run(spec, workdir=str(tmp_path), label="t")
    assert len(rounds) == 2                      # never converges -> runs the full budget
    assert best is not None and "score" in best
    # the meter requirement (3/4) is violated by the 4/4 stub -> recorded as a failed requirement
    assert any(c["pass"] is False for c in best["requirement_checks"])


# ---- difficulty grader + training detector ----
def test_difficulty_grader_orders_easy_below_hard(tmp_path):
    from libretto.tasks.education import grade as G
    easy = tmp_path / "easy.txt"
    easy.write_text("KEY: C major | METER: 4/4 | TEMPO: 70 | GRID: 16th | BARS: 2\nVOICES: Piano\n"
                    "@1 [C]\n  Piano: C4@1>16\n@2 [C]\n  Piano: C4@1>16\n")
    hard = tmp_path / "hard.txt"
    hard.write_text("KEY: E minor | METER: 4/4 | TEMPO: 160 | GRID: 16th | BARS: 2\nVOICES: Piano\n"
                    "@1 [Em]\n  Piano: E4@1>1 G4@2>1 B4@3>1 E5@4>1 D#5@7>1 B4@8>1 G4@11>1 C5@15>1\n"
                    "@2 [B]\n  Piano: B4@3>1 F#5@7>1 D#5@11>1 B4@13>2 G4@15>2\n")
    ge = G.difficulty_grade(easy, key="C major"); gh = G.difficulty_grade(hard, key="E harmonic minor")
    assert ge["score_0_100"] < gh["score_0_100"]
    assert 1 <= ge["grade_1_10"] <= gh["grade_1_10"] <= 10
    assert set(ge["factors"]) >= {"tempo", "syncopation", "note_values", "melodic_range_leaps", "meter"}


def test_detect_training_tags(tmp_path):
    from libretto.tasks.education import grade as G
    p = tmp_path / "x.txt"
    p.write_text("KEY: C major | METER: 3/4 | TEMPO: 138 | GRID: 16th | BARS: 2\nVOICES: Piano\n"
                 "@1 [C]\n  Piano: C4@1>4 E4@3>4 G4@7>4\n@2 [G]\n  Piano: G4@1>4 D4@5>4 B3@9>4\n")
    t = G.detect_training(p)
    tags = t["training_tags"]
    assert any(s.startswith("meter:3/4") for s in tags)
    assert any(s.startswith("tempo:") for s in tags)
    assert any(s.startswith("key:") for s in tags)
    assert any(s.startswith("syncopation:") for s in tags)
