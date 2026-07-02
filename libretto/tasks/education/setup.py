#!/usr/bin/env python3
"""setup.py — build a single-channel-piano practice-piece prompt from a RequirementSpec.

A RequirementSpec (dict) — only `level` + `key` are required; everything else optional:
  level: beginner | intermediate | advanced
  key:   "A harmonic minor" / "C major" / ...
  concept_ids: [...]            explicit kb_theory concepts; if omitted, AUTO-SCALED by level + dimensions
  dimensions:  ["rhythm","chord",...]   focus the auto-scaler
  n_concepts:  int              how many concepts to drill (default 3)
  meter: "3/4"                  time-signature requirement
  tempo: "fast" | 140 | [120,160]   tempo requirement (word, bpm, or range)
  rhythm_feel: "fast"|"slow"|"moderate"   rhythm density/value requirement
  require_chords: ["Dm","A7","Gm"]    chords that MUST appear
  dominant_chord: "Dm"          the chord that should be used MOST
  dynamics: "start soft, crescendo to the cadence"   requested dynamics (render-layer overlay, not gated)
  bars: int ; title: str ; with_exemplar: bool
  realistic: bool               REALISTIC-drill preset (alias: hybrid): a non-trivial, MONOPHONIC single line
                                that roams the whole staff range over time (engraves on ONE staff with clef
                                changes) with mixed rhythms. ALWAYS anchors to the ADVANCED level (52 bars,
                                5 concepts) and sets single_line + grand_staff + rhythm_mix. Use a MAJOR key.
  single_line: bool             require a monophonic line (≈one note at a time; arpeggiate harmony) so the
                                score reads on a single clef-changing staff, not a grand staff.
  grand_staff: bool | dict      require the line to TRAVEL across both registers AND cover most in-key pitches
                                over the range; dict may override {low_max, high_min, min_low_frac,
                                min_high_frac, cover_lo, cover_hi, cover_min}.
  rhythm_mix: bool              require several rhythm patterns, interleaved & non-repetitive (no AAAA blocks).
"""
import json
from pathlib import Path

import libretto
from . import retrieval as R
from . import curriculum as C

SHARED = (Path(libretto.__file__).resolve().parent / "generation" / "prompts" / "_shared.md")
LEVEL_BARS = {"beginner": 8, "intermediate": 12, "advanced": 16}

# Single-clef register bands (MIDI). treble = stay in/above middle C and reach up; bass = stay in/below and
# reach down. cover_* = the in-key pitches a reader meets in that clef, ≥cover_min of which must appear.
CLEF_BANDS = {
    "treble": dict(mode="treble", cover_lo=60, cover_hi=84, cover_min=0.6, hi_min=79, lo_floor=55),
    "bass":   dict(mode="bass",   cover_lo=36, cover_hi=60, cover_min=0.6, lo_max=41, hi_ceil=64),
}


def resolve_spec(spec):
    """Fill defaults + auto-scale concepts. Returns a normalized spec (does not mutate the input)."""
    s = dict(spec)
    s.setdefault("level", "beginner")
    # REALISTIC drill preset (alias: 'hybrid'): a realistic, non-trivial practice piece — a mix of different
    # rhythms AND notes across almost the whole register a reader meets on the grand staff (both clefs). Detected
    # early so it can raise the concept/bar budget before auto-scaling.
    realistic = bool(s.pop("realistic", False) or s.pop("hybrid", False))
    if realistic:
        s["level"] = "advanced"                 # realistic drills ALWAYS anchor to the advanced level
        s.setdefault("rhythm_mix", True)
        # concepts suited to a single line: rhythm + melody + ARPEGGIATED harmony (no block chords / polyphony).
        s.setdefault("dimensions", ["rhythm", "melody", "chord"])
        s.setdefault("clef", "changing")        # CLEF is a user choice (like key): treble|bass|grand|changing
    # CLEF option -> notation mode + register requirement:
    #   treble / bass = ONE line kept in that clef's register (engraves in that clef);
    #   grand         = spans BOTH registers (grand staff, may stack);
    #   changing      = ONE line roaming the whole range, so a SINGLE staff changes clef.
    clef = s.get("clef")
    if clef in ("grand", "changing"):
        s.setdefault("grand_staff", True)
        if clef == "changing":
            s.setdefault("single_line", True)
    elif clef in ("treble", "bass"):
        s.setdefault("single_line", True)
        s["clef_band"] = dict(CLEF_BANDS[clef])
    ld = C.level_defaults(s["level"])           # richer, higher-difficulty defaults per level
    s.setdefault("with_exemplar", True)
    s.setdefault("bars", ld["bars"])
    if realistic:
        s["bars"] = max(s["bars"], 52)          # a full-length piece (50+ bars) — room to cover the whole staff
                                                # and work through many DIFFERENT rhythms without repeating
    s.setdefault("meter", "4/4")
    s.setdefault("range_min", ld["range_min"])          # melodic-range floor (semitones)
    s.setdefault("melody_interest", ld["melody_interest"])
    s.setdefault("syncopation", ld["syncopation"])      # a baseline of syncopation for musical interest
    s.setdefault("tempo", ld["tempo"])
    if not s.get("concept_ids"):
        s["concept_ids"] = C.autoscale(s["level"], s.get("dimensions"), s.get("n_concepts", ld["n_concepts"]),
                                       offset=int(s.get("variant", 0)))
    bpm, rng = C.tempo_bpm(s["tempo"]); s["tempo_bpm"] = bpm; s["tempo_range"] = list(rng)
    if "rhythm_feel" in s:
        s["rhythm_feel_target"] = C.rhythm_feel_target(s["rhythm_feel"])
    if s.get("syncopation"):
        s["syncopation_band"] = C.syncopation_band(s["syncopation"])
    # Grand-staff band: the piece must reach the bass register AND the treble register (so the score engraves
    # onto BOTH clefs) AND actually COVER most of the in-key pitches across that range (hit almost all the notes
    # a reader meets on the staff, not just the two extremes). Stays ONE `Piano` voice — the notation splits it
    # by pitch, so no two-voice gate change is needed.
    if s.get("grand_staff"):
        gs = s["grand_staff"] if isinstance(s.get("grand_staff"), dict) else {}
        s["grand_staff_band"] = dict(low_max=gs.get("low_max", 48), high_min=gs.get("high_min", 76),
                                     min_low_frac=gs.get("min_low_frac", 0.15),
                                     min_high_frac=gs.get("min_high_frac", 0.15),
                                     cover_lo=gs.get("cover_lo", 48), cover_hi=gs.get("cover_hi", 76),
                                     cover_min=gs.get("cover_min", 0.6))
    s["rhythm_mix"] = bool(s.get("rhythm_mix"))
    s["single_line"] = bool(s.get("single_line"))
    return s


def _requirements_text(s):
    L = [f"- LEVEL: {s['level']}",
         f"- KEY / SCALE: {s['key']} — stay in this key/scale (only a listed device may add chromatic notes).",
         f"- TIME SIGNATURE (METER): {s['meter']} — write the bars in this meter.",
         f"- TEMPO: ~{s['tempo_bpm']} bpm" + (f" ({s['tempo']})" if isinstance(s.get('tempo'), str) else "")]
    if s.get("rhythm_feel"):
        ft = s["rhythm_feel_target"]
        L.append(f"- RHYTHM FEEL: {s['rhythm_feel']} — "
                 + ("predominantly short note values (eighths/sixteenths) and a busy onset flow."
                    if ft["feel"] == "fast" else
                    "predominantly long note values and a calm, sparse onset flow." if ft["feel"] == "slow"
                    else "a balanced mix of note values."))
    if s.get("syncopation_band"):
        lo, hi = s["syncopation_band"]
        L.append(f"- SYNCOPATION AMOUNT: {s['syncopation']} — about {int(lo*100)}–{int(hi*100)}% of note onsets "
                 f"should land OFF the beat (off-beat slots 3/7/11/15…), the rest on the beat. "
                 + ("Keep it subtle." if hi <= 0.32 else "Lean into the off-beats." if lo >= 0.50 else "A clear but balanced amount."))
    if s.get("require_chords"):
        L.append(f"- CHORDS TO USE: include these chords (as the `[chord]` of bars): {', '.join(s['require_chords'])}.")
    if s.get("dominant_chord"):
        L.append(f"- MOST-USED CHORD: {s['dominant_chord']} should appear MORE than any other (the home chord).")
    if s.get("range_min"):
        L.append(f"- MELODIC RANGE: span at least {s['range_min']} semitones across the piece — move around the "
                 f"keyboard, don't sit on a few notes (a real but comfortable {s['level']} range).")
    if s.get("melody_interest"):
        L.append("- MELODY: make it musically interesting — mostly stepwise motion BUT with some leaps for "
                 "shape, change direction (rise and fall), and avoid repeating one note. (Pedagogical interest, "
                 "NOT strict classical voice-leading — leaps and repetition are fine in moderation.)")
    if s.get("single_line"):
        L.append("- SINGLE LINE: write ONE melodic line — ONE note at a time, NO simultaneous chords "
                 "(arpeggiate any harmony as broken chords, one note at a time; do NOT stack pitches with `+`). "
                 "This is a monophonic reading study.")
    clef = s.get("clef")
    if clef == "treble":
        L.append("- CLEF / REGISTER: TREBLE clef. Keep the line in the treble register — middle C (C4) and "
                 "ABOVE, roaming up to around E5–C6 — and visit most of the notes a reader meets on the treble "
                 "staff. Don't drop far below middle C.")
    elif clef == "bass":
        L.append("- CLEF / REGISTER: BASS clef. Keep the line in the bass register — middle C (C4) and BELOW, "
                 "roaming down to around F2–C3 — and visit most of the notes a reader meets on the bass staff. "
                 "Don't climb far above middle C.")
    elif clef == "grand":
        L.append("- CLEF / RANGE (GRAND STAFF): span BOTH registers — low notes in the bass (around C3–F2) AND "
                 "high notes in the treble (around E5–C6), covering most in-key pitches across the range, so the "
                 "score fills both the treble and bass staves.")
    elif s.get("grand_staff_band"):   # 'changing'
        L.append("- CLEF / RANGE (roams the WHOLE staff OVER TIME): the single line must TRAVEL across almost "
                 "the whole range — dip DOWN into the bass register (around C3–F2) in some passages and climb UP "
                 "into the treble (around E5–C6) in others, through the middle, so the engraved score CHANGES "
                 "CLEF as the line descends and rises. Visit most pitches a reader meets; don't sit in one octave.")
    if s.get("rhythm_mix"):
        L.append("- RHYTHM (MIXED & NON-REPETITIVE): use SEVERAL different rhythm patterns and INTERLEAVE them, "
                 "varying the rhythm from bar to bar. Do NOT repeat one rhythmic pattern over and over, and do "
                 "NOT group all of one pattern then switch (no 'AAAA BBBB' blocks) — mix the patterns throughout "
                 "so there is no obvious separation between them.")
    if s.get("dynamics"):
        L.append(f"- DYNAMICS (performance overlay — shape while playing; not written in the note data): {s['dynamics']}.")
    L.append(f"- LENGTH: ~{s['bars']} bars.")
    return "\n".join(L)


def build_prompt(spec, corrections=None):
    s = resolve_spec(spec)
    ctx = R.build_context(s["concept_ids"], with_exemplar=s["with_exemplar"])
    shared = SHARED.read_text(encoding="utf-8")
    corr = ""
    if corrections:
        corr = ("\n\n## REVISION FEEDBACK (your previous attempt missed these — fix them, keep everything else):\n"
                + "\n".join(f"  - {c}" for c in corrections) + "\n")
    prompt = f"""# EDUCATION — single-channel PIANO practice piece
Compose a SHORT practice piece for a music learner. ONE voice named `Piano` only (chords via `+`).
Clean, readable, PLAYABLE at the stated level.

## GRAMMAR FORMAT (shared)
{shared}

{ctx['text']}

## YOUR TASK — requirements
{_requirements_text(s)}
- The piece MUST clearly EXERCISE every required-challenge concept above (that is the point of the drill).
- NOVELTY: invent your OWN melody/figuration. Do NOT reproduce the example snippets or any existing song —
  copy is checked.{corr}

## OUTPUT CONTRACT
Return ONLY the grammar block (no prose/fences): line 1 `KEY: ... | METER: {s['meter']} | TEMPO: {s['tempo_bpm']}
| GRID: 16th | BARS: <N>`, line 2 `VOICES: Piano`, then all numbered bar blocks.
"""
    case = dict(spec=s, key=s["key"], level=s["level"], meter=s["meter"],
                tempo_bpm=s["tempo_bpm"], tempo_range=s["tempo_range"],
                rhythm_feel_target=s.get("rhythm_feel_target"),
                syncopation=s.get("syncopation"), syncopation_band=s.get("syncopation_band"),
                range_min=s.get("range_min"), melody_interest=s.get("melody_interest"),
                require_chords=s.get("require_chords"), dominant_chord=s.get("dominant_chord"),
                dynamics=s.get("dynamics"), grand_staff_band=s.get("grand_staff_band"),
                rhythm_mix=s.get("rhythm_mix"), single_line=s.get("single_line"),
                clef=s.get("clef"), clef_band=s.get("clef_band"),
                concept_ids=ctx["concept_ids"], exemplar_ids=ctx["exemplar_ids"],
                shown_grammars=ctx["shown_grammars"], bars=s["bars"])
    return prompt, case


def write_case(spec, outdir, corrections=None):
    out = Path(outdir); out.mkdir(parents=True, exist_ok=True)
    prompt, case = build_prompt(spec, corrections=corrections)
    name = spec.get("title", "practice").replace(" ", "_")
    (out / f"genprompt_{name}.txt").write_text(prompt, encoding="utf-8")
    (out / f"{name}_case.json").write_text(json.dumps(case, indent=2))
    return out / f"genprompt_{name}.txt", case
