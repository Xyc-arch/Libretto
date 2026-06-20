#!/usr/bin/env python3
"""
midi_to_grammar.py — turn a MIDI file into a compact, LLM-readable text score.

Python does all the parsing; an LLM only ever sees the text output, so it can read
and judge the music cheaply instead of choking on raw MIDI bytes.

CLI:
    python3 midi_to_grammar.py input.mid [-o out.txt] [--grid 16] [--keep-drums]
                                         [--max-bars N] [--anonymize]

Pipeline:
    1. Parse MIDI; detect key (score.analyze("key")), time signature, tempo.
    2. Quantize by ROUNDING each note to a grid slot (grid 16 -> 16th-note slots,
       0.25 quarter-lengths each): bar number, onset slot in bar, duration in slots
       (min 1). The rounding *is* the quantization — kills MIDI micro-timing.
    3. Drop percussion by default (channel 10 / index 9, Unpitched notes, or a part
       named drum/perc). --keep-drums includes it as a voice; drums never affect chords.
    4. Group simultaneous onsets in a part into one chord token (pitch+pitch+...).
    5. Per bar, at HALF-BAR resolution, label a best-fit chord from all pitched voices:
       always a name (major/minor/dim/aug, +7) — added/passing tones are tolerated.
       One label when the halves agree, "X | Y" on a mid-bar change, "-" when silent.
       (See FORMAT.md / the midi-to-grammar skill for the exact algorithm.)

Output (bar-anchored, note names + durations, not note-on/off pairs):
    KEY: A major | METER: 4/4 | TEMPO: 105 | GRID: 16th | BARS: 32
    VOICES: Melody, Bass, Piano
    @1 [A]
      Melody: A4@1>4 C#5@5>4 E5@9>8
      Bass:   A2@1>8 E2@9>8
      Piano:  A3+C#4+E4@1>16
    @2 [D7 | A]
      ...
  @N = bar number, [X] = chord ("X | Y" = mid-bar change, "-" = silent), Pitch@P>D = note
  (P = onset slot 1-indexed in bar, D = duration in slots), A+C#+E@P>D = simultaneous notes.
"""
import argparse
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from music21 import chord, converter, instrument, meter, midi, note, tempo
from music21.midi import translate as _miditranslate

# Generic instrument/role words that describe a part WITHOUT revealing the song or
# artist. When --anonymize is on, voice labels made only of these (or digits) are
# kept (role is useful, not identifying); anything else becomes "PartN".
INSTRUMENT_WORDS = {
    "melody", "lead", "vocal", "vocals", "voice", "voc", "choir", "chorus", "harmony",
    "bass", "piano", "keys", "keyboard", "key", "organ", "rhodes", "wurli", "epiano",
    "guitar", "gtr", "acoustic", "electric", "rhythm", "strings", "string", "synth",
    "pad", "brass", "horn", "horns", "sax", "trumpet", "trombone", "flute", "clarinet",
    "oboe", "violin", "viola", "cello", "harp", "drums", "drum", "perc", "percussion",
    "kit", "bells", "marimba", "vibes", "vibraphone", "accordion", "harmonica", "banjo",
    "fiddle", "fx", "arp", "solo", "fill", "intro", "verse", "chorus", "left", "right",
}

# Pitch-class -> name (sharp spelling for sharp/neutral keys, flats for flat keys).
SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLAT = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]

# Triad templates as intervals above the root. The labeler picks the best-fitting
# one (it does not require an exact match) and then adds a 7th if present.
TRIADS = (("", (0, 4, 7)), ("m", (0, 3, 7)), ("dim", (0, 3, 6)), ("aug", (0, 4, 8)))
_QUAL_PREF = {"": 0, "m": 1, "dim": 2, "aug": 3}   # tie-break preference order

# Adaptive grid: resolutions in slots-per-whole-note. Binary 4/8/16/32 are
# quarter/8th/16th/32nd; triplet 6/12/24 are quarter/8th/16th-note triplets.
_BINARY_GRIDS = (4, 8, 16, 32)
_TRIPLET_GRIDS_ORD = (6, 12, 24)
_TRIPLET_GRIDS = frozenset(_TRIPLET_GRIDS_ORD)


def grid_label(grid_tuple) -> str:
    """(slots_per_whole, is_triplet) -> compact label, e.g. (16, False)->'16th', (12, True)->'12t'."""
    g, trip = grid_tuple
    return f"{g}t" if trip else f"{g}th"


def _collapses(voice_onsets, g):
    """True if, at grid g, any voice has two DISTINCT onsets landing on one slot.

    Notes sharing an onset are legitimately merged into one chord token, so duplicate
    onset times are de-duplicated first — only genuinely separate onsets can collapse.
    """
    slot_ql = 4.0 / g
    for onsets in voice_onsets:
        seen = set()
        for o in sorted(set(onsets)):
            k = int(round(o / slot_ql))
            if k in seen:
                return True
            seen.add(k)
    return False


def _avg_residual(voice_onsets, g):
    """Mean distance (quarter-lengths) from each distinct onset to its nearest grid-g slot."""
    slot_ql = 4.0 / g
    total, n = 0.0, 0
    for onsets in voice_onsets:
        for o in set(onsets):
            k = round(o / slot_ql)
            total += abs(o - k * slot_ql)
            n += 1
    return total / n if n else 0.0


def choose_bar_grid(voice_onsets, bar_ql):
    """Pick a bar's grid from its per-voice within-bar onset offsets (quarter-lengths).

    1. Take the coarsest BINARY grid (4→8→16→32) at which no voice collapses two
       distinct onsets into one slot (falls back to 32 if even that collapses).
    2. Switch to the coarsest TRIPLET grid (6→12→24) only if it does not collapse and
       fits the onsets clearly better than the binary choice (mean residual < half),
       i.e. the bar is genuinely triplet rather than binary-with-a-stray-note.

    Returns (slots_per_whole, is_triplet); None if the bar has no onsets.
    """
    if not any(voice_onsets):
        return None
    g_bin = next((g for g in _BINARY_GRIDS if not _collapses(voice_onsets, g)), 32)
    r_bin = _avg_residual(voice_onsets, g_bin)
    if r_bin > 0.02:                       # binary doesn't explain the onsets well
        for g in _TRIPLET_GRIDS_ORD:
            if not _collapses(voice_onsets, g) and _avg_residual(voice_onsets, g) < 0.5 * r_bin:
                return (g, True)
    return (g_bin, False)


# --------------------------------------------------------------------------- #
# Percussion detection (same rule used by the score tool).
# --------------------------------------------------------------------------- #
def is_percussion(part) -> bool:
    """True if a part is drums: unpitched notes, an UnpitchedPercussion instrument,
    MIDI channel 10 (index 9), or a drum/perc name. (Format-0 MIDIs are demuxed into
    real per-channel parts first, so the GM drum channel is its own part here.)"""
    if part.recurse().getElementsByClass(("Unpitched", "PercussionChord")):
        return True
    for inst in part.recurse().getElementsByClass(instrument.Instrument):
        if isinstance(inst, instrument.UnpitchedPercussion):
            return True
        if getattr(inst, "midiChannel", None) in (9, 10):
            return True
    name = (part.partName or "")
    inst = part.getInstrument(returnDefault=False)
    if inst is not None and inst.instrumentName:
        name += " " + inst.instrumentName
    return any(w in name.lower() for w in ("drum", "perc"))


# --------------------------------------------------------------------------- #
# MIDI loading with format-0 / single-track demux by channel.
# --------------------------------------------------------------------------- #
def _is_channel_voice(event):
    return type(getattr(event, "type", None)).__name__ == "ChannelVoiceMessages"


def _needs_demux(mf) -> bool:
    """A file needs channel-demux if it is format 0, or a single music track that
    multiplexes more than one MIDI channel (so all instruments collapse into one part)."""
    if mf.format == 0:
        return True
    music = [t for t in mf.tracks if any(_is_channel_voice(e) for e in t.events)]
    if len(music) == 1:
        chans = {e.channel for e in music[0].events if _is_channel_voice(e)}
        return len(chans) > 1
    return False


def _demux_by_channel(mf):
    """Rebuild a collapsed MIDI as a format-1 file with ONE track per MIDI channel, so
    music21 yields real per-instrument parts (matching how format-1 files already parse).
    Meta/tempo/time-sig events go to a shared track 0. midiChannel is NOT forced — the GM
    drum channel keeps its unpitched-note content, which is_percussion already detects."""
    meta_abs = []                  # [(abs_tick, event)]
    chan_abs = {}                  # channel -> [(abs_tick, event)]
    for tr in mf.tracks:
        abst = 0
        for e in tr.events:
            if type(e).__name__ == "DeltaTime":
                abst += e.time
                continue
            fam = type(getattr(e, "type", None)).__name__
            if fam == "MetaEvents" and e.type.name == "END_OF_TRACK":
                continue
            if _is_channel_voice(e):
                chan_abs.setdefault(e.channel, []).append((abst, e))
            else:
                meta_abs.append((abst, e))

    # keep only channels that actually sound a note
    channels = [c for c in sorted(chan_abs)
                if any(ev.type.name == "NOTE_ON" for _, ev in chan_abs[c])]

    def build(idx, abs_events):
        t = midi.MidiTrack(idx)
        evs, prev = [], 0
        for abst, e in abs_events:
            dt = midi.DeltaTime(t); dt.time = abst - prev; dt.channel = getattr(e, "channel", 1)
            e.track = t
            evs.append(dt); evs.append(e)
            prev = abst
        dt = midi.DeltaTime(t); dt.time = 0
        eot = midi.MidiEvent(t); eot.type = midi.MetaEvents.END_OF_TRACK; eot.data = b""
        evs.append(dt); evs.append(eot)
        t.events = evs
        return t

    nf = midi.MidiFile()
    nf.format = 1
    nf.ticksPerQuarterNote = mf.ticksPerQuarterNote
    nf.tracks = [build(0, meta_abs)] + [build(i + 1, chan_abs[c]) for i, c in enumerate(channels)]
    return nf


def _read_score(midi_path):
    """Load a MIDI as a music21 Score, demuxing format-0 / single-track-multichannel files
    into per-channel parts so voice structure is independent of MIDI file format."""
    try:
        mf = midi.MidiFile()
        mf.open(str(midi_path))
        mf.read()
        mf.close()
    except Exception:  # noqa: BLE001
        return converter.parse(str(midi_path))
    if _needs_demux(mf):
        try:
            return _miditranslate.midiFileToStream(_demux_by_channel(mf))
        except Exception:  # noqa: BLE001
            pass
    return converter.parse(str(midi_path))


# --------------------------------------------------------------------------- #
# Naming helpers.
# --------------------------------------------------------------------------- #
def pc_name(pc: int, flats: bool) -> str:
    return (FLAT if flats else SHARP)[pc % 12]


def pitch_token_names(el):
    """Pitch names (with octave) for a Note/Chord; placeholder for unpitched."""
    out = []
    for p in getattr(el, "pitches", ()):
        out.append((p.midi, p.nameWithOctave.replace("-", "b")))
    if not out:                       # unpitched percussion hit
        disp = getattr(el, "displayName", None) or "x"
        out.append((-1, str(disp)))
    return out


def _words(text):
    return [w for w in re.split(r"[^a-z0-9]+", text.lower()) if w]


def voice_name(part, idx, perc, used, anonymize=False, forbidden=frozenset()) -> str:
    """A readable, unique voice label.

    With anonymize=True, labels that could reveal the song/artist are replaced with
    a generic "PartN": a label is kept only if it is purely instrument/role words
    (see INSTRUMENT_WORDS) and shares no word with `forbidden` (tokens from the
    title/artist). Percussion stays "Drums" (never identifying).
    """
    if perc:
        name = "Drums"
    else:
        name = (part.partName or "").strip()
        if not name:
            inst = part.getInstrument(returnDefault=False)
            if inst is not None and inst.instrumentName:
                name = inst.instrumentName.strip()
        if not name:
            name = f"Voice{idx + 1}"

    if anonymize and not perc:
        ws = _words(name)
        leaks = any(w in forbidden for w in ws)
        safe = bool(ws) and all(w.isdigit() or w in INSTRUMENT_WORDS for w in ws)
        if leaks or not safe:
            name = f"Part{idx + 1}"

    base, n = name, 2
    while name in used:
        name = f"{base}#{n}"
        n += 1
    used.add(name)
    return name


# --------------------------------------------------------------------------- #
# Chord labelling — best-fit, always commits to a name (no uncertain output).
# --------------------------------------------------------------------------- #
def label_chord(weights, flats: bool) -> str:
    """Best-fit chord label from a {pitch-class: duration-weight} profile.

    Scores every root×triad by how much weight its chord tones cover, picks the best
    (tie-break: heavier root, then major>minor>dim>aug), then appends a 7th if that
    note is a real chord member. Always returns a name — added/passing tones are
    tolerated rather than forcing an "uncertain" set. '-' only when nothing sounds.
    """
    if not weights:
        return "-"
    best = None  # (coverage, root_weight, -qual_pref, root, suffix, tones)
    for root in range(12):
        for suffix, tpl in TRIADS:
            tones = [(root + i) % 12 for i in tpl]
            coverage = sum(weights.get(t, 0.0) for t in tones)
            key = (coverage, weights.get(root, 0.0), -_QUAL_PREF[suffix])
            if best is None or key > best[0]:
                best = (key, root, suffix, tones)
    _, root, suffix, tones = best

    # Is a seventh a real chord member (vs. a brief passing tone)? Compare to the
    # root's weight (stable) so short melodic 7ths don't flip the label.
    ref = weights.get(root, 0.0) or max((weights.get(t, 0.0) for t in tones), default=0.0)

    def strong(pc):
        return ref > 0 and weights.get(pc, 0.0) >= 0.5 * ref

    base = pc_name(root, flats)
    if suffix == "":
        return base + ("7" if (strong((root + 10) % 12) or strong((root + 11) % 12)) else "")
    if suffix == "m":
        return base + ("m7" if strong((root + 10) % 12) else "m")
    if suffix == "dim":
        if strong((root + 9) % 12):
            return base + "dim7"
        return base + ("m7" if strong((root + 10) % 12) else "dim")
    return base + "aug"


def root_quality(label: str) -> str:
    """Chord label with any trailing 7th stripped (so A7 and A, Dm7 and Dm match)."""
    if label == "-":
        return label
    for seventh, base in (("dim7", "dim"), ("m7", "m"), ("7", "")):
        if label.endswith(seventh):
            return label[: -len(seventh)] + base
    return label


# --------------------------------------------------------------------------- #
# Quantization: absolute offset -> (bar, onset-slot, duration-slots).
# --------------------------------------------------------------------------- #
def quantize(off, ql, bar_ql, slot_ql, slots_per_bar):
    bar_idx = int(off // bar_ql)
    in_bar = off - bar_idx * bar_ql
    slot = int(round(in_bar / slot_ql)) + 1          # 1-indexed within the bar
    if slot > slots_per_bar:                          # rounded past the barline
        bar_idx += 1
        slot = 1
    dur = max(1, int(round(ql / slot_ql)))
    return bar_idx + 1, slot, dur


def encode(midi_path: Path, grid: int, keep_drums: bool, max_bars, anonymize=False):
    score = _read_score(midi_path)
    # Tokens (from title + artist folder) that a voice label must not echo.
    forbidden = set(_words(f"{midi_path.stem} {midi_path.parent.name}")) if anonymize else frozenset()

    # Global attributes.
    try:
        analyzed = score.analyze("key")
        key_str = f"{analyzed.tonic.name.replace('-', 'b')} {analyzed.mode}"
        flats = analyzed.sharps < 0
    except Exception:                                 # noqa: BLE001
        analyzed, key_str, flats = None, "?", False
    ts = score.recurse().getElementsByClass(meter.TimeSignature).first()
    meter_str = ts.ratioString if ts else "4/4"
    bar_ql = ts.barDuration.quarterLength if ts else 4.0
    mm = score.recurse().getElementsByClass(tempo.MetronomeMark).first()
    tempo_str = str(int(mm.number)) if (mm and mm.number) else "?"

    # Split parts into voices-to-print and harmony parts (harmony is always pitched).
    all_parts = list(score.parts)
    perc_flags = [is_percussion(p) for p in all_parts]
    harmony_parts = [p for p, d in zip(all_parts, perc_flags) if not d]
    if keep_drums:
        voice_parts = list(zip(all_parts, perc_flags))
    else:
        voice_parts = [(p, d) for p, d in zip(all_parts, perc_flags) if not d]

    if not any(not d for _, d in voice_parts) and not keep_drums:
        return None  # nothing pitched survived

    # When drums are dropped, never extract unpitched/percussion notes — this strips drum
    # hits out of an otherwise-melodic collapsed part (format-0 MIDIs).
    note_classes = (("Note", "Chord", "Unpitched", "PercussionChord")
                    if keep_drums else ("Note", "Chord"))

    # ---- Choose the grid for each bar ---------------------------------------
    # Fixed mode (grid is an int): every bar uses it — byte-identical to before.
    # Adaptive mode (grid == "adaptive"): each bar gets the coarsest grid that
    # represents its onsets without collapsing distinct onsets into one slot.
    adaptive = (grid == "adaptive")
    per_bar_grid = {}                      # bar -> (slots_per_whole, is_triplet)
    if adaptive:
        bar_onsets = defaultdict(lambda: defaultdict(list))   # bar -> vidx -> [in-bar offset]
        for vidx, (part, _perc) in enumerate(voice_parts):
            for el in part.flatten().getElementsByClass(note_classes):
                off = float(el.offset)
                bidx = int(off // bar_ql)
                bar_onsets[bidx + 1][vidx].append(off - bidx * bar_ql)
        for bar, vmap in bar_onsets.items():
            sel = choose_bar_grid(list(vmap.values()), bar_ql)
            if sel is not None:
                per_bar_grid[bar] = sel
        if per_bar_grid:                   # default = most common grid (deterministic)
            counts = Counter(per_bar_grid.values())
            default_grid = sorted(counts.items(),
                                  key=lambda kv: (-kv[1], kv[0][1], kv[0][0]))[0][0]
        else:
            default_grid = (16, False)
    else:
        default_grid = (int(grid), False)

    def grid_of(bar):
        return per_bar_grid.get(bar, default_grid)

    # Build per-voice events, quantizing each note with its bar's grid.
    used_names = set()
    voices = []          # (name, {bar: {slot: [dur, [(midi,name)...]]}})
    for idx, (part, perc) in enumerate(voice_parts):
        name = voice_name(part, idx, perc, used_names, anonymize, forbidden)
        bars = defaultdict(dict)
        for el in part.flatten().getElementsByClass(note_classes):
            g, _trip = grid_of(int(float(el.offset) // bar_ql) + 1)
            slot_ql = 4.0 / g
            slots_per_bar = max(1, int(round(bar_ql / slot_ql)))
            bar, slot, dur = quantize(el.offset, el.quarterLength,
                                      bar_ql, slot_ql, slots_per_bar)
            cell = bars[bar].get(slot)
            names = pitch_token_names(el)
            if cell is None:
                bars[bar][slot] = [dur, list(names)]
            else:
                cell[0] = max(cell[0], dur)
                cell[1].extend(names)
        voices.append((name, bars))

    # Chord labels at HALF-BAR resolution, weighted by how long each pitch sounds in
    # each half (overlap, so sustained chords count in both). Adaptive: a bar shows
    # one chord when both halves agree, two ("X | Y") only when harmony changes.
    half_ql = bar_ql / 2.0
    half_pcs = defaultdict(lambda: defaultdict(float))   # (bar, half 0|1) -> pc -> weight
    for part in harmony_parts:
        for el in part.flatten().getElementsByClass(("Note", "Chord")):
            off = float(el.offset)
            ql = float(el.quarterLength)
            bar_idx = int(off // bar_ql)
            base = bar_idx * bar_ql
            for h in (0, 1):
                ws = base + h * half_ql
                overlap = min(ws + half_ql, off + ql) - max(ws, off)
                if overlap > 0:
                    for p in el.pitches:
                        half_pcs[(bar_idx + 1, h)][p.pitchClass] += overlap

    def bar_label(bar):
        a = label_chord(half_pcs.get((bar, 0), {}), flats)
        b = label_chord(half_pcs.get((bar, 1), {}), flats)
        if a == b:
            return a
        if a == "-":
            return b
        if b == "-":
            return a
        if root_quality(a) == root_quality(b):       # same chord, 7th-only difference
            return a if len(a) >= len(b) else b       # keep the richer (7th) label
        return f"{a} | {b}"

    # Total bars.
    end = 0.0
    for part, _ in voice_parts:
        end = max(end, part.flatten().highestTime)
    total_bars = max(1, int(math.ceil(end / bar_ql)))
    if max_bars:
        total_bars = min(total_bars, max_bars)

    # Render text.
    label_w = max((len(n) for n, _ in voices), default=0)
    grid_field = (f"{grid_label(default_grid)} (adaptive)"
                  if adaptive else f"{int(grid)}th")
    lines = [
        f"KEY: {key_str} | METER: {meter_str} | TEMPO: {tempo_str} | "
        f"GRID: {grid_field} | BARS: {total_bars}",
        "VOICES: " + ", ".join(n for n, _ in voices),
    ]
    for bar in range(1, total_bars + 1):
        gt = grid_of(bar)
        ann = ("" if (not adaptive or gt == default_grid)
               else f" (grid:{gt[0]}{'t' if gt[1] else ''})")
        lines.append(f"@{bar} [{bar_label(bar)}]{ann}")
        for name, bars in voices:
            cells = bars.get(bar)
            if not cells:
                continue
            toks = []
            for slot in sorted(cells):
                dur, names = cells[slot]
                names = sorted(set(names))                  # dedup, ascending pitch
                pitches = "+".join(n for _, n in names)
                toks.append(f"{pitches}@{slot}>{dur}")
            lines.append(f"  {name.ljust(label_w)}: {' '.join(toks)}")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="MIDI -> compact LLM-readable text score.")
    ap.add_argument("midi", help="Input .mid file")
    ap.add_argument("-o", "--output", help="Write text here (else stdout)")
    ap.add_argument("--grid", default="16",
                    help="Grid resolution: an int = fixed slots per whole note "
                         "(default 16 = 16th notes), or 'adaptive' = per-bar grid.")
    ap.add_argument("--keep-drums", action="store_true", help="Include percussion as a voice")
    ap.add_argument("--max-bars", type=int, help="Cap output to N bars")
    ap.add_argument("--anonymize", action="store_true",
                    help="Scrub track names that could reveal the song/artist")
    args = ap.parse_args()

    grid = args.grid
    if grid != "adaptive":
        try:
            grid = int(grid)
            if grid <= 0:
                raise ValueError
        except ValueError:
            print(f"--grid must be a positive int or 'adaptive' (got {args.grid!r})",
                  file=sys.stderr)
            return 1

    src = Path(args.midi)
    if not src.exists():
        print(f"File not found: {src}", file=sys.stderr)
        return 1

    text = encode(src, grid, args.keep_drums, args.max_bars, args.anonymize)
    if text is None:
        print("No pitched content (file looks all-percussion). "
              "Re-run with --keep-drums to include the drum voice.", file=sys.stderr)
        return 1

    tokens = len(text) // 4  # rough chars/4 estimate
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"Wrote {args.output}  (~{tokens} tokens, {len(text)} chars)", file=sys.stderr)
    else:
        sys.stdout.write(text)
        print(f"\n[~{tokens} tokens, {len(text)} chars]", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
