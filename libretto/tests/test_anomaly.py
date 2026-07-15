#!/usr/bin/env python3
"""Tests for the anomaly-detection task: injectors are PURE (never mutate the source), make exactly one
change, report correct ground truth, and produce valid, measurably-different anomalous copies."""
import json

import libretto
from libretto.tasks.anomaly import inject as I
from libretto.tasks.anomaly import build_cases as B

GR = libretto.data_root() / "grammar"
SID = "song_0820"


def _src():
    return (GR / f"{SID}.txt").read_text()


def test_injectors_are_pure_and_single_change():
    src = _src()
    for kind in I.KINDS:
        new, meta = I.inject(src, kind, seed=0)
        assert new is not None and meta["kind"] == kind and meta["bar"] >= 1
        assert (GR / f"{SID}.txt").read_text() == src, "injector mutated the source corpus"
        a, b = src.splitlines(), new.splitlines()
        diff = sum(1 for i in range(min(len(a), len(b))) if a[i] != b[i]) + abs(len(a) - len(b))
        assert diff == 1, f"{kind} changed {diff} lines (want exactly 1)"


def test_seed_varies_the_bar():
    src = _src()
    bars = {I.inject(src, "out_of_key", seed=s)[1]["bar"] for s in range(5)}
    assert len(bars) >= 3, "seed should inject into different bars"


def test_out_of_key_note_is_actually_out_of_key():
    from libretto.tasks.education.measure import scale_pcs
    new, meta = I.inject(_src(), "out_of_key", seed=0)
    _, pcs, _ = scale_pcs(meta["key"])
    orig, changed = meta["change"].split("->")
    assert I._midi(orig) % 12 in pcs and I._midi(changed) % 12 not in pcs


def test_build_cases_balanced_pure_and_valid(tmp_path):
    cases = B.build_cases(n=4, seed=1, out=str(tmp_path))
    anom = [c for c in cases.values() if c["has_anomaly"]]
    clean = [c for c in cases.values() if not c["has_anomaly"]]
    assert len(anom) == len(clean) == 4
    assert all(c["bar"] and c["kind"] != "none" for c in anom)
    assert all(c["bar"] is None and c["kind"] == "none" for c in clean)
    # every anomalous copy decodes to valid MIDI
    from libretto.core import grammar_to_midi as G
    for cid, c in cases.items():
        if c["has_anomaly"]:
            G.decode(str(tmp_path / f"{cid}.txt"), str(tmp_path / "_t.mid"))


if __name__ == "__main__":
    test_injectors_are_pure_and_single_change()
    test_seed_varies_the_bar()
    test_out_of_key_note_is_actually_out_of_key()
    print("anomaly inject tests passed")


def test_all_six_kinds_and_voice_leading():
    src = _src()
    for kind in ("voice_crossing", "parallel_fifths"):
        new, meta = I.inject(src, kind, seed=1)
        assert new is not None and meta["kind"] == kind
        assert (GR / f"{SID}.txt").read_text() == src  # pure
    assert set(I.KINDS) >= {"out_of_key", "wrong_bass", "dissonance", "meter_glitch",
                            "voice_crossing", "parallel_fifths"}


def test_excerpt_cases_are_short(tmp_path):
    cases = B.build_cases(n=3, seed=3, out=str(tmp_path), excerpt_bars=16)
    for cid in cases:
        txt = (tmp_path / f"{cid}.txt").read_text()
        nbars = sum(1 for l in txt.splitlines() if l.startswith("@"))
        assert nbars <= 16


def test_clean_source_is_verifiably_clean():
    from libretto.tasks.anomaly.clean_source import clean_piece
    from libretto.tasks.anomaly.verify import is_clean
    for key, seed in [("C", 1), ("G", 2), ("D", 3), ("Bb", 4)]:
        t = clean_piece(key, bars=10, seed=seed)
        assert t is not None, f"failed to sample clean {key}"
        clean, flags = is_clean(t)
        assert clean, f"generated chorale not clean: {flags}"


def test_verifier_catches_each_injected_kind():
    from libretto.tasks.anomaly.clean_source import clean_piece
    from libretto.tasks.anomaly.verify import is_clean
    src = clean_piece("C", bars=12, seed=1)
    assert is_clean(src)[0]                      # clean before injection
    for kind in ("out_of_key", "wrong_bass", "meter_glitch", "voice_crossing"):
        new, meta = I.inject(src, kind, seed=1)
        if new is None:
            continue
        assert not is_clean(new)[0], f"verifier missed injected {kind}"
