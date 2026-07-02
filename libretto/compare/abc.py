"""libretto.compare.abc — emit the SAME music as ABC (relative durations) and Libretto (absolute slots) from one
event list, and verify both re-parse to an identical (voice, onset, pitch) set.

Events are tuples ``(voice, onset_beat_abs, dur_beats, midi)`` on an eighth grid (durations/onsets are multiples
of 0.5 beat), which is what the benchmark generator produces. This is intentionally the controlled-stimulus path,
not a general renderer for arbitrary corpus songs (which use a 16th grid and accidentals).
"""
import re
import tempfile
from pathlib import Path

NAT = {0: "C", 2: "D", 4: "E", 5: "F", 7: "G", 9: "A", 11: "B"}
SHARP = {1: 0, 3: 2, 6: 5, 8: 7, 10: 9}                 # accidental pc -> natural a semitone below (^ = sharp)


def midi_abc(m):
    """MIDI -> ABC pitch token (C4 = uppercase C; c = C5; ',' lowers, ''' raises; '^' = sharp)."""
    pc, octv = m % 12, m // 12 - 1
    if pc in NAT:
        letter, acc = NAT[pc], ""
    else:
        letter, acc = NAT[SHARP[pc]], "^"
    if octv >= 5:
        body = letter.lower() + "'" * (octv - 5)
    elif octv == 4:
        body = letter
    else:
        body = letter + "," * (4 - octv)
    return acc + body


def sci(m):
    """MIDI -> scientific pitch token used in Libretto (e.g. C4). Accidentals as sharps."""
    pc, octv = m % 12, m // 12 - 1
    return (NAT[pc] if pc in NAT else NAT[SHARP[pc]] + "#") + str(octv)


def emit_abc(events, voices, bars, marks=frozenset()):
    """ABC (L:1/8): one [V:x] line per voice, '|' barlines, 'z' rests; '*' marks a note in `marks`={(voice,onset)}."""
    lines = ["X:1", "M:4/4", "L:1/8", "K:C"]
    for vn in voices:
        evs = sorted([e for e in events if e[0] == vn], key=lambda e: e[1])
        toks, cursor, bar = [], 0.0, 0
        for v, onset, dur, m in evs:
            b = int(onset // 4)
            while bar < b:
                toks.append("|"); bar += 1; cursor = bar * 4
            if onset > cursor + 1e-6:
                r = round((onset - cursor) * 2)
                toks.append("z" + (str(r) if r != 1 else "")); cursor = onset
            u = round(dur * 2)
            star = "*" if (v, round(onset, 3)) in marks else ""
            toks.append(star + midi_abc(m) + (str(u) if u != 1 else ""))
            cursor = onset + dur
        lines.append(f"[V:{vn}] " + " ".join(toks) + " |")
    return "\n".join(lines)


def _chord_name(pcs):
    NAMES = {0: "C", 2: "D", 4: "E", 5: "F", 7: "G", 9: "A", 11: "B"}
    for root in sorted(pcs):
        iv = {(p - root) % 12 for p in pcs}
        if {0, 4, 7} <= iv:
            return NAMES.get(root, "?")
        if {0, 3, 7} <= iv:
            return NAMES.get(root, "?") + "m"
    return NAMES.get(min(pcs), "?") if pcs else "-"


def emit_libretto(events, voices, bars, marks=frozenset()):
    """Libretto grammar (16th grid): token P@slot>dur; '@n [chord]' per bar; '*' marks a note in `marks`."""
    lines = [f"KEY: C major | METER: 4/4 | TEMPO: 120 | GRID: 16th | BARS: {bars}",
             "VOICES: " + ", ".join(voices)]
    for b in range(bars):
        pcs = {m % 12 for v, o, d, m in events if int(o // 4) == b and abs(o - b * 4) < 1e-6}
        lines.append(f"@{b + 1} [{_chord_name(pcs)}]")
        for vn in voices:
            evs = sorted([e for e in events if e[0] == vn and int(e[1] // 4) == b], key=lambda e: e[1])
            if not evs:
                continue
            toks = []
            for v, onset, dur, m in evs:
                slot = int(round((onset - b * 4) * 4)) + 1
                star = "*" if (v, round(onset, 3)) in marks else ""
                toks.append(f"{star}{sci(m)}@{slot}>{int(round(dur * 4))}")
            lines.append(f"  {vn}: " + " ".join(toks))
    return "\n".join(lines)


def source_set(events):
    return {(v, round(o, 3), m) for v, o, d, m in events}


def parse_libretto(text):
    """Re-parse an emitted Libretto string via the frozen codec -> {(voice, abs-onset, midi)}."""
    from libretto.core import Song
    d = Path(tempfile.mkdtemp())
    p = d / "l.txt"
    p.write_text(text, encoding="utf-8")
    return {(e["voice"], round(e["onb"] + (e["bar"] - 1) * 4, 3), e["midi"]) for e in Song(str(p)).events}


def abc_note_count(text):
    """Count melody notes in an emitted ABC string (music21). Used only as a fidelity cross-check."""
    from music21 import converter, note
    sc = converter.parse(text, format="abc")
    return len(list(sc.recurse().getElementsByClass(note.Note)))


def roundtrip_ok(events, voices, bars):
    """True iff the emitted Libretto re-parses to exactly the source (voice, onset, pitch) set."""
    return parse_libretto(emit_libretto(events, voices, bars)) == source_set(events)
