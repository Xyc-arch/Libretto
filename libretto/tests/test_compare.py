"""Tests for libretto.compare — deterministic cost contrast + tool-free reading benchmark."""
import libretto
from libretto.compare import benchmark as B
from libretto.compare import encoding_cost
from libretto.compare.abc import emit_abc, emit_libretto, roundtrip_ok, source_set, parse_libretto


# ---------------------------------------------------------------- deterministic cost
def _fixture_events():
    # 2 voices, 1 bar. RH: 4 notes at beats 0,1.5,2,3 ; LH: 2 notes at beats 0,2 (onsets absolute).
    return [("RH", 0.0, 1.5, 72), ("RH", 1.5, 0.5, 71), ("RH", 2.0, 1.0, 69), ("RH", 3.0, 1.0, 67),
            ("LH", 0.0, 2.0, 48), ("LH", 2.0, 2.0, 43)]


def test_encoding_cost_matches_hand_computation():
    ev = [dict(voice=v, bar=1, onb=o, dur=d, midi=m) for v, o, d, m in _fixture_events()]
    c = encoding_cost(ev)
    assert (c.n_notes, c.n_voices, c.n_bars) == (6, 2, 1)
    # onset_recovery = (4-1) + (2-1) = 4 ; edit_blast = 4*3/2 + 2*1/2 = 6+1 = 7
    assert c.onset_recovery == 4
    assert c.edit_blast == 7
    # vertical_align: qbeats = {0,1.5,2,3}; RH before each: 0,1,2,3 =6 ; LH before each: 0,1,1,2 =4 -> 10
    assert c.vertical_align == 10
    assert c.libretto == 0                                   # absolute slot: always 0


def test_libretto_cost_is_zero_on_real_corpus_song():
    g = sorted((libretto.data_root() / "grammar").glob("*.txt"))
    c = encoding_cost(str(g[46]))
    assert c.libretto == 0
    assert c.onset_recovery > 0 and c.vertical_align >= 0     # ABC-style cost is real and non-trivial


# ---------------------------------------------------------------- ABC / Libretto emission round-trip
def test_emit_roundtrips_to_identical_note_set():
    ev = _fixture_events()
    assert roundtrip_ok(ev, ["RH", "LH"], 1)
    # Libretto re-parse equals the source (voice, onset, pitch) set exactly
    assert parse_libretto(emit_libretto(ev, ["RH", "LH"], 1)) == source_set(ev)


def test_abc_and_libretto_encode_same_music():
    ev = _fixture_events()
    abc, lib = emit_abc(ev, ["RH", "LH"], 1), emit_libretto(ev, ["RH", "LH"], 1)
    assert "[V:RH]" in abc and "[V:LH]" in abc
    assert lib.count("@1") >= 1 and "RH:" in lib and "LH:" in lib


# ---------------------------------------------------------------- benchmark oracle + scoring
def test_benchmark_oracle_high_signal():
    items = B.build(B.HIGH_SIGNAL, seeds=(0, 1))
    assert items
    ok, detail = B.oracle(items)
    assert ok, detail
    assert detail["impossible"] == 0


def test_benchmark_oracle_full():
    ok, detail = B.oracle(B.build(B.FULL, seeds=(0,)))
    assert ok, detail


def test_hallucination_set_oracle_and_prompts():
    items = B.build_hallucination(seeds=range(2), scales=(8,))
    ok, _ = B.oracle(items)
    assert ok
    ap, lp = B.prompts(items[0], quick=True)
    assert "quick read" in ap.lower() and "--- SCORE ---" in ap and "--- SCORE ---" in lp


def test_impossible_flags_out_of_meter_only():
    it = {"task": "T1", "bars": 8}
    assert B.impossible(it, "onset", "bar 8 beat 7") is True        # beat 7 cannot exist in 4/4
    assert B.impossible(it, "onset", "bar 9 beat 1") is True        # bar past the passage
    assert B.impossible(it, "onset", "bar 8 beat 3.5") is False     # a real in-bar position
    assert B.impossible(it, "onset", "bar 8 beat 4.5") is False


def test_score_one_canonicalizes_pitch_and_onset():
    assert B.score_one("onset", "bar 2 beat 2.5", "bar 2 beat 2.5", "abc")
    assert not B.score_one("onset", "bar 2 beat 2", "bar 2 beat 2.5", "abc")
    # ABC letters vs scientific: 'G,,' == G2, 'd' == D5
    assert B.score_one("pitch_each", "RH:A, LH:G,,", {"RH": "A4", "LH": "G2"}, "abc")
    assert B.score_one("intervals", "S:+2, A:-3", {"S": 2, "A": -3}, "lib")
    # T6 representation-specific truth
    gt = {"abc": "bar 2 beat 4.5", "lib": "bar 2 beat 4"}
    assert B.score_one("onset", "bar 2 beat 4.5", gt, "abc")
    assert B.score_one("onset", "bar 2 beat 4", gt, "lib")
    assert not B.score_one("onset", "bar 2 beat 4", gt, "abc")
