#!/usr/bin/env python3
"""
grammar_to_midi.py — DECODER: the grammar encoder run in reverse (grammar text -> playable .mid).

Parses a grammar file's header (KEY/METER/TEMPO/GRID/BARS/VOICES) and every
`Pitch@Position>Duration` token, converts each to a MIDI note, and writes a multi-track .mid
(one track/instrument per voice) via pretty_midi. It reuses the SAME note-level parser the analysis
pipeline uses (understanding_probe.Song), so the decode is exactly the grammar the rest of the system
reads — guaranteeing structural round-trip fidelity.

Per token: note name (F2, Bb4) -> MIDI number; absolute tick from (bar-1)*ticks_per_bar +
(pos-1)*ticks_per_slot using the header (and any per-bar (grid:G)); length = duration*ticks_per_slot;
note-on at start, note-off at start+length. Chord tokens (P+P+P) -> simultaneous note-ons.

TIMBRE / DYNAMICS / DRUMS are now preserved when the grammar carries them:
  - VOICES "[prog=N]" -> that GM program; "[drums]" -> percussion channel (is_drum=True).
    A bare voice name (old-format grammar) still falls back to name-based program guessing.
  - a token's optional "^V" suffix sets that note's velocity; absent -> default 85.

KNOWN LOSSES (honest): still a STRUCTURALLY-FAITHFUL deterministic decode, NOT the original
performance. It faithfully reconstructs PITCH, TIMING (onset), DURATION, VOICE SEPARATION, and now
(when declared) INSTRUMENT PROGRAM, COARSE VELOCITY, and DRUM routing. It does NOT recover:
MICRO-TIMING / human feel (quantized away at encode time), or fine velocity (coarsely bucketed).

Overlapping same-pitch notes within a voice (a pedal note re-articulated while still sounding) can't
share one MIDI channel — the two note-offs collide and truncate the longer note. The decoder handles
this by splitting such a voice across LANES (separate channels, same name/program) so both survive;
because the name is preserved, they re-read as one voice and duration round-trips exactly. This
previously shifted the duration of a few % of notes in pad-heavy arrangements; it now round-trips
losslessly (full corpus: 0 notes lost/invented/reshaped).
"""
import re
import sys
from collections import defaultdict, Counter
from pathlib import Path

import pretty_midi

from .understanding_probe import Song

VELOCITY = 85
# voice-name keyword -> General MIDI program (0-indexed). First substring match wins.
VOICE_PROGRAMS = [
    ("backvox", 52), ("back vox", 52), ("vox", 52), ("choir", 52), ("vocal", 52),
    ("bass", 33),                                   # Electric Bass (finger)
    ("rhodes", 4), ("e.piano", 4), ("epiano", 4), ("keys", 4), ("key", 4),  # Electric Piano
    ("synth", 81),                                  # Lead 2 (sawtooth)
    ("pad", 89), ("strings", 48), ("string", 48),   # Pad 2 / String Ensemble
    ("horn", 61), ("brass", 61),                    # Brass Section
    ("sax", 65), ("trumpet", 56), ("flute", 73),
    ("guitar", 27),                                 # Electric Guitar (clean)
    ("organ", 16),
    ("melody", 65), ("lead", 65),                   # a lead (Alto Sax)
    ("piano", 0),
]
DEFAULT_PROGRAM = 0                                  # Acoustic Grand Piano


def program_for(voice):
    v = voice.lower()
    for kw, prog in VOICE_PROGRAMS:
        if kw in v:
            return prog
    return DEFAULT_PROGRAM


def _split_same_pitch_overlaps(events):
    """Distribute one voice's events into LANES so no lane sounds the same pitch twice at once.

    MIDI can't hold two same-pitch notes on one channel (their note-offs collide and truncate the
    longer one). A voice that pedals a pitch while re-articulating it needs those overlapping copies
    on separate channels. Greedy first-fit in onset order → minimal lanes: a voice with no same-pitch
    overlap stays a single lane. Only same-pitch overlap forces a new lane (other pitches coexist
    freely on one channel)."""
    lanes = []                                   # each: {"events": [...], "end": {pitch: latest_end}}
    for e in sorted(events, key=lambda x: (x["abs"], x["midi"])):
        p = int(e["midi"]); start = e["abs"]; end = e["abs"] + max(e["dur"], 1e-3)
        placed = False
        for lane in lanes:
            if lane["end"].get(p, -1.0) <= start + 1e-9:      # no same-pitch note still sounding
                lane["events"].append(e); lane["end"][p] = end; placed = True
                break
        if not placed:
            lanes.append({"events": [e], "end": {p: end}})
    return [lane["events"] for lane in lanes]


def tempo_of(path):
    first = Path(path).read_text(encoding="utf-8").splitlines()[0]
    m = re.search(r"TEMPO:\s*([\d.]+)", first)
    return float(m.group(1)) if m else 100.0


def decode(grammar_path, out_path):
    """grammar file -> .mid (structurally faithful). Returns (bpm, n_notes, n_voices)."""
    song = Song(grammar_path)
    bpm = tempo_of(grammar_path)
    spb = 60.0 / bpm                                 # seconds per quarter-note beat
    # resolution 480 ticks/quarter divides every grid exactly: binary (480/32=15) AND
    # triplet (480/3=160) — so triplet onsets/durations land on exact ticks, no drift.
    pm = pretty_midi.PrettyMIDI(initial_tempo=bpm, resolution=480)
    by_voice = defaultdict(list)
    for e in song.events:
        by_voice[e["voice"]].append(e)
    # keep header VOICES order, then any extras
    order = [v for v in song.voices if v in by_voice] + [v for v in by_voice if v not in song.voices]
    n_notes = 0
    for voice in order:
        # Timbre: use the GM program declared in the grammar ("[prog=N]") if present, and route
        # "[drums]" voices to the percussion channel; otherwise fall back to name-based guessing.
        is_drum = voice in getattr(song, "drum_voices", ())
        program = getattr(song, "voice_programs", {}).get(voice)
        if program is None:
            program = 0 if is_drum else program_for(voice)
        # Split same-pitch overlaps across lanes (separate channels) so sustained pedal + re-strike
        # both survive; every lane keeps the SAME name so it re-reads as one voice on round-trip.
        for lane_events in _split_same_pitch_overlaps(by_voice[voice]):
            inst = pretty_midi.Instrument(program=program, name=voice, is_drum=is_drum)
            for e in lane_events:
                start = e["abs"] * spb
                end = (e["abs"] + max(e["dur"], 1e-3)) * spb     # ensure positive length
                vel = e.get("vel") or VELOCITY                   # per-note velocity if declared
                # clamp to the valid MIDI range — a stray out-of-range pitch/velocity (a generator can
                # emit one) must not make the whole piece un-writable (mido rejects bytes outside 0..127)
                pitch = min(127, max(0, int(e["midi"])))
                vel = min(127, max(1, int(vel)))
                inst.notes.append(pretty_midi.Note(velocity=vel, pitch=pitch,
                                                   start=start, end=end))
                n_notes += 1
            pm.instruments.append(inst)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    pm.write(str(out_path))
    return bpm, n_notes, len(order)


def roundtrip_check(grammar_path, tmp_mid):
    """Decode grammar -> MIDI, read MIDI back, compare note sets (pitch/onset/dur/voice)."""
    song = Song(grammar_path)
    bpm = tempo_of(grammar_path)
    spb = 60.0 / bpm
    decode(grammar_path, tmp_mid)
    pm = pretty_midi.PrettyMIDI(str(tmp_mid))
    # grammar note multiset: (voice, midi, onset_beat, dur_beat) rounded
    def key(voice, midi, onset_b, dur_b):
        # round to 2 dp (~0.01 beat ≈ 5 ticks): absorbs float jitter from the beats->sec->beats
        # round-trip on irrational triplet durations (k/3 beats), while staying far finer than the
        # smallest possible slot (0.125 beat), so genuinely distinct notes never collide.
        return (voice, int(midi), round(onset_b, 2), round(dur_b, 2))
    g = Counter(key(e["voice"], e["midi"], e["abs"], max(e["dur"], 1e-3)) for e in song.events)
    d = Counter()
    res = pm.resolution
    for inst in pm.instruments:
        for n in inst.notes:
            # compare in TICKS (inverts the write exactly) rather than seconds, which carry
            # pretty_midi's integer-microsecond tempo rounding that drifts at large onsets.
            st, en = pm.time_to_tick(n.start), pm.time_to_tick(n.end)
            d[key(inst.name, n.pitch, st / res, (en - st) / res)] += 1
    missing = g - d           # in grammar, not in decoded MIDI
    extra = d - g             # in decoded MIDI, not in grammar
    return len(song.events), sum(d.values()), missing, extra


def main():
    args = sys.argv[1:]
    if args and args[0] == "--validate":
        gp = args[1] if len(args) > 1 else "grammar/song_0047.txt"
        n_g, n_d, missing, extra = roundtrip_check(gp, "/tmp/_rt_check.mid")
        print(f"ROUND-TRIP VALIDATION on {gp}")
        print(f"  grammar notes: {n_g} | decoded-MIDI notes: {n_d}")
        print(f"  mismatches: {len(missing)} missing, {len(extra)} extra")
        if missing or extra:
            for k, c in list(missing.items())[:8]:
                print(f"    MISSING {k} x{c}")
            for k, c in list(extra.items())[:8]:
                print(f"    EXTRA   {k} x{c}")
            print("  RESULT: MISMATCH")
        else:
            print("  RESULT: EXACT MATCH — pitch/onset/duration/voice all round-trip.")
        return
    # render mode: grammar_to_midi.py <out_dir> <file1.txt> [file2.txt ...]
    out_dir = Path(args[0]); files = args[1:]
    for f in files:
        stem = Path(f).stem
        bpm, n, nv = decode(f, out_dir / f"{stem}.mid")
        print(f"  rendered {stem}.mid  ({n} notes, {nv} voices, {bpm:.0f} bpm)")


if __name__ == "__main__":
    main()
