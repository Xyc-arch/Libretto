"""Tests for libretto.validation — run: `python -m pytest libretto/tests/test_validation.py`.

Hermetic by default: the registry, perturbation (re-fingerprinted), and statistics tests need no audio.
The end-to-end test is skipped unless fluidsynth + a soundfont are present, and uses a deterministic
FakeJudge so it never needs the AudioBox venv.
"""
import json
import shutil

import pytest

import libretto
from libretto.core.fingerprint import profile
from libretto.validation import (
    LEVERS, UNCOVERED, canonical_axes, lever, perturb, register_lever,
    sign_test_p, summarize, validate,
)

DATA = libretto.data_root()
GRAMMAR = DATA / "grammar"
CANON = canonical_axes()


# --------------------------------------------------------------------------- #
# registry + coverage (the 24-of-28 story)
# --------------------------------------------------------------------------- #
def test_coverage_is_24_of_28():
    canon = set(CANON)
    levered = canon & set(LEVERS)
    assert len(canon) == 28
    assert len(levered) == 24, f"expected 24 levered canonical axes, got {len(levered)}"


def test_uncovered_axes_are_canonical_and_explained():
    assert set(UNCOVERED) == {"har_chord_change_rate", "har_vocab_density",
                              "har_fourth_motion_rate", "form_section_per100bars"}
    for axis, reason in UNCOVERED.items():
        assert axis in CANON, f"{axis} not in canonical set"
        assert axis not in LEVERS, f"{axis} should NOT have a lever"
        assert len(reason) > 20, f"{axis} needs a real reason"


def test_levered_plus_uncovered_covers_all_canonical():
    accounted = set(LEVERS) | set(UNCOVERED)
    assert set(CANON) <= accounted, f"unaccounted canonical axes: {set(CANON) - accounted}"


# --------------------------------------------------------------------------- #
# perturbation actually moves the target axis (re-fingerprinted)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("axis", ["tex_voice_count", "rhy_onset_density_per_bar",
                                  "tex_mean_simultaneity", "mel_voice_range"])
def test_lever_moves_target_axis_monotonically(axis, tmp_path):
    text = (GRAMMAR / "song_0100.txt").read_text()
    push = LEVERS[axis].push
    pcts = []
    for dose in (0.0, 0.5, 1.0):
        t = perturb(text, axis, dose)
        f = tmp_path / f"{axis}_{dose}.txt"
        f.write_text(t)
        pcts.append(profile(f)[0][axis]["percentile"])
    # toward the extreme: high-push percentile should not DECREASE; low-push should not INCREASE
    extremity = pcts if push == "high" else [-p for p in pcts]
    assert extremity[-1] >= extremity[0], f"{axis} ({push}) did not move toward its extreme: {pcts}"
    assert extremity[-1] > extremity[0] + 1e-9 or pcts[0] in (0, 100), \
        f"{axis} ({push}) did not move at all: {pcts}"


def test_register_custom_axis():
    @lever("test_dummy_axis", push="high")
    def _push(text, dose):
        return text
    try:
        assert "test_dummy_axis" in LEVERS
        assert LEVERS["test_dummy_axis"].push == "high"
        assert perturb("x\n", "test_dummy_axis", 0.0) == "x\n"  # dose 0 = unchanged
    finally:
        LEVERS.pop("test_dummy_axis", None)


def test_perturb_unknown_axis_raises():
    with pytest.raises(KeyError):
        perturb("x", "no_such_axis", 1.0)


# --------------------------------------------------------------------------- #
# pure statistics
# --------------------------------------------------------------------------- #
def test_sign_test_p():
    assert sign_test_p(8, 8) == pytest.approx(1 / 256)
    assert sign_test_p(0, 0) == 1.0
    assert sign_test_p(4, 8) == pytest.approx(163 / 256)  # P(X>=4) under Binom(8, .5)


def test_summarize_flags_consistent_negative_axis():
    # axisA: every song's CE falls monotonically with dose -> within_rho = -1, validated.
    # axisB: CE rises -> positive, not validated.
    rows = []
    for song in ("s1", "s2", "s3"):
        for dose, ce_a, ce_b in [(0.0, 8.0, 5.0), (0.5, 7.0, 6.0), (1.0, 6.0, 7.0)]:
            rows.append(dict(song=song, axis="axisA", push="low", dose=dose, entangled=0, CE=ce_a))
            rows.append(dict(song=song, axis="axisB", push="high", dose=dose, entangled=0, CE=ce_b))
    res = {a.axis: a for a in summarize(rows, primary="CE", min_songs=3)}
    assert res["axisA"].within_rho == pytest.approx(-1.0)
    assert res["axisA"].validated and res["axisA"].n == 3 and res["axisA"].n_neg == 3
    assert res["axisA"].delta == pytest.approx(-2.0)            # 6 - 8
    assert res["axisB"].within_rho == pytest.approx(1.0)
    assert not res["axisB"].validated


def test_summarize_drops_constant_ce_song():
    # a song whose CE never changes across doses is dropped (edit inaudible) -> n counts only the rest.
    rows = []
    for dose, ce in [(0.0, 7.0), (0.5, 7.0), (1.0, 7.0)]:
        rows.append(dict(song="flat", axis="ax", push="low", dose=dose, entangled=0, CE=ce))
    for dose, ce in [(0.0, 8.0), (0.5, 7.0), (1.0, 6.0)]:
        rows.append(dict(song="moves", axis="ax", push="low", dose=dose, entangled=0, CE=ce))
    a = summarize(rows, primary="CE", min_songs=1)[0]
    assert a.n == 1 and "flat" not in a.per_song and "moves" in a.per_song


# --------------------------------------------------------------------------- #
# end-to-end with a deterministic FakeJudge (skips if no renderer)
# --------------------------------------------------------------------------- #
class FakeJudge:
    """Scores by clip energy so identical clips score identically and perturbed clips differ — no model."""
    primary = "CE"
    METRICS = ("CE",)

    def score(self, wav_paths):
        import wave
        import numpy as np
        out = []
        for p in wav_paths:
            with wave.open(str(p), "rb") as w:
                a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64)
            out.append({"path": p, "CE": float(np.sqrt((a ** 2).mean()) / 1000.0) if len(a) else 0.0})
        return out


@pytest.mark.skipif(shutil.which("fluidsynth") is None, reason="fluidsynth not installed")
def test_validate_end_to_end_fake_judge():
    try:
        res = validate(songs=["song_0100"], axes=["tex_voice_count"], judge=FakeJudge(),
                       doses=[0.0, 1.0], clip_seconds=20, progress=lambda *a: None)
    except FileNotFoundError as e:
        pytest.skip(str(e))  # no soundfont
    assert res.primary == "CE"
    assert len(res.axes) == 1 and res.axes[0].axis == "tex_voice_count"
    assert res.coverage()["canonical"] == 28
    assert all(c in res.rows[0] for c in ("song", "axis", "dose", "CE"))
