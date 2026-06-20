"""libretto deterministic-core tests — run: `python -m pytest libretto/tests` or `python libretto/tests/test_core.py`.

These exercise ONLY the reproducible layer (no LLM). They pin the frozen contract:
round-trip note-faithfulness, 29-axis fingerprint shape, copy_risk self-match, and determinism.
"""
import json
import tempfile
from pathlib import Path

import libretto
from libretto.core import Song, metrics_for, copy_risk
from libretto.core import grammar_to_midi as g2m

DATA = libretto.data_root()
GRAMMAR = DATA / "grammar"
CANON = json.loads((DATA / "corpus_distribution_314.json").read_text())
AXES = CANON["axes_order"]
SAMPLE = GRAMMAR / "song_0001.txt"


def test_distribution_is_29_axis():
    assert len(AXES) == 29, f"expected 29 retained axes, got {len(AXES)}"
    assert "within_song_variation" in AXES


def test_roundtrip_note_faithful():
    """Decode a corpus grammar -> MIDI -> read back: no notes lost or invented (decoder fidelity).

    Uses a binary-grid reference song so the (voice,pitch,onset,dur) keys compare exactly. NB: on
    triplet-heavy songs roundtrip_check's 2-decimal keying cannot represent k/3 beats identically and
    reports spurious mismatches — a keying artifact, NOT lost notes (the encoder-side fidelity audit
    independently shows decode-side pitch preservation at ~100%; see log/FIDELITY_AUDIT.md)."""
    ref = GRAMMAR / "song_0003.txt"
    with tempfile.TemporaryDirectory() as td:
        n_ev, n_dec, missing, extra = g2m.roundtrip_check(ref, Path(td) / "rt.mid")
    assert sum(missing.values()) == 0, f"notes lost on round-trip: {list(missing)[:3]}"
    assert sum(extra.values()) == 0, f"notes invented on round-trip: {list(extra)[:3]}"
    assert n_dec == n_ev


def test_metrics_cover_all_retained_axes():
    m = metrics_for(Song(SAMPLE), SAMPLE)
    for a in AXES:
        assert a in m, f"axis {a} not computed"
    assert isinstance(m["within_song_variation"], float)


def test_metrics_are_deterministic():
    a = metrics_for(Song(SAMPLE), SAMPLE)
    b = metrics_for(Song(SAMPLE), SAMPLE)
    for k in AXES:
        assert a[k] == b[k], f"non-deterministic axis {k}: {a[k]} != {b[k]}"


def test_copy_risk_self_match_high():
    """A corpus song slid against the corpus must find a near-identical match (self)."""
    r = copy_risk(SAMPLE)
    assert r["copy_risk"] >= 0.9, f"self-match too low: {r['copy_risk']}"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
    print("all core tests passed")
