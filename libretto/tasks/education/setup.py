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
"""
import json
from pathlib import Path

import libretto
from . import retrieval as R
from . import curriculum as C

SHARED = (Path(libretto.__file__).resolve().parent / "generation" / "prompts" / "_shared.md")
LEVEL_BARS = {"beginner": 8, "intermediate": 12, "advanced": 16}


def resolve_spec(spec):
    """Fill defaults + auto-scale concepts. Returns a normalized spec (does not mutate the input)."""
    s = dict(spec)
    s.setdefault("level", "beginner")
    ld = C.level_defaults(s["level"])           # richer, higher-difficulty defaults per level
    s.setdefault("with_exemplar", True)
    s.setdefault("bars", ld["bars"])
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
                dynamics=s.get("dynamics"), concept_ids=ctx["concept_ids"], exemplar_ids=ctx["exemplar_ids"],
                shown_grammars=ctx["shown_grammars"], bars=s["bars"])
    return prompt, case


def write_case(spec, outdir, corrections=None):
    out = Path(outdir); out.mkdir(parents=True, exist_ok=True)
    prompt, case = build_prompt(spec, corrections=corrections)
    name = spec.get("title", "practice").replace(" ", "_")
    (out / f"genprompt_{name}.txt").write_text(prompt, encoding="utf-8")
    (out / f"{name}_case.json").write_text(json.dumps(case, indent=2))
    return out / f"genprompt_{name}.txt", case
