# SKILL: education — single-channel piano practice pieces for learners

Generate a SHORT, single-voice (`Piano`) practice score+MIDI that drills a learner's **required challenge**
(a rhythm, key/scale, chord, progression, melodic device, texture, articulation, or form). Difficulty is set
by which `kb_theory` concepts you combine + the level/length.

## Retrieval-first pipeline (browse theory, then style)
1. **browse kb_theory** (`retrieval.py`) — map the requested challenge to `kb_theory` concept IDs
   (`by_category`/`search`/`concept`); each entry carries WHAT + CHALLENGE + a renderable single-voice-piano
   GRAMMAR example. See `data/kb_theory/SKILL.md` for the challenge-dimension → ID map.
2. **auto-scale by level** (`curriculum.py autoscale`) — if `concept_ids` aren't given, pick a concept set for
   the difficulty LEVEL (beginner/intermediate/advanced) spread across the requested DIMENSIONS.
3. **(optional) classical exemplar** — `classical_exemplar()` pulls a short excerpt of the most prototypical
   CLASSICAL corpus song for phrasing/contour flavour (style reference only — output stays single-voice piano).
4. **setup** (`setup.py build_prompt`) — assemble the prompt from a **RequirementSpec** (below).
5. **generate** — feed the prompt to a Generator (single voice `Piano`).
6. **refine loop** (`refine_loop.py RefinementLoop`) — generate → measure → if a challenge/requirement/key/
   novelty check failed, append corrective feedback and regenerate (≤ max_iter, pick best). Leakage-free.
7. **measure** (`measure.py`) — the gate below.  8. **render** — `core.decode_to_midi`.

## Comprehensive by DEFAULT (2026-07-09)
Every drill is now comprehensive unless the caller opts out — driven by the standard reading a learner meets:
- **VARIED tempo + meter** — `tempo`/`meter` default to a level-appropriate ladder cycled by `variant`, so a
  batch covers the MAJOR speed range and several time signatures (not one fixed 4/4). Explicit `tempo`/`meter`
  still win. (`curriculum.TEMPO_LADDER` / `METER_LADDER`.)
- **MIXED rhythms** — `rhythm_mix` defaults **True**: several interleaved rhythmic figures with different note
  durations in every drill (set `rhythm_mix=False` to opt out).
- **FULL pitch coverage** — `clef` defaults to `changing`, so the single line roams the whole reading range =
  the 5 staff lines + 3 ledger LINES and 3 ledger SPACES above AND below each clef. That rule is exactly
  **bass A1(33)→g′ G4(67)**, **treble f F3(53)→e‴ E6(88)**, union **A1..E6**. `STAFF_BANDS` scales how much of
  that range a drill must span+cover by level (advanced reaches the full A1↔E6 extremes). Pin `clef=treble|bass`
  for a single-clef study.

## RequirementSpec (user-specific control)
Only `level` + `key` required; the rest optional — the system verifies the ones you set:
`level`, `key` ("D harmonic minor"), `meter` ("3/4" time signature), `tempo` ("fast" | 138 | [120,156]),
`rhythm_feel` ("fast"/"slow"/"moderate" → note-density/value), `require_chords` (["Dm","Gm","A"]),
`dominant_chord` ("Dm" → must be most-used), `dynamics` (free text → render-layer overlay, reported not
gated), `concept_ids` / `dimensions` / `n_concepts` (else auto-scaled), `bars`, `title`.
`realistic: true` (alias `hybrid`) — a **realistic, non-trivial** drill (use a MAJOR key): sets `grand_staff`
+ `rhythm_mix` and raises the concept/bar budget, so the piece mixes rhythms and covers almost the whole staff.
`grand_staff` / `rhythm_mix` can also be set individually (dict form overrides the band/coverage thresholds).

## Gate (measure.measure)
- **SINGLE-CHANNEL** — exactly one voice.
- **IN-KEY** — ≥88% of notes belong to the requested key/scale (a small chromatic allowance for the device).
- **CHALLENGE** — the requested concept(s) are actually exercised, via per-category detectors (syncopation
  off-beat ratio, note-value presence, triplet/12t bars, scale membership, block-chord simultaneity, melodic
  leap/stepwise interval profile, arpeggio/broken texture). Concepts with no auto-detector are reported as
  manual-review (don't fail the gate).
- **REQUIREMENTS** — the explicit RequirementSpec constraints are verified: time-signature (header METER),
  tempo (header in range), required chords present, dominant chord most-used, rhythm feel (median note
  duration + onsets/bar). Dynamics is reported as a performance overlay (not gated). For `grand_staff` /
  `realistic`: **span+coverage** — notes reach both the bass (<middle C) and treble (≥middle C) registers with
  a real share of each, AND cover ≥60% of the in-key pitches across the staff range (hits most notes a reader
  meets, not just the extremes). For `rhythm_mix`: **mixed & non-repetitive** — several distinct per-bar
  rhythms, longest identical run ≤2 bars, and the rhythm changes bar-to-bar ≥50% of the time (interleaved,
  no "AAAA BBBB" blocks).
- **NOVEL (copy control)** — two signals:
  - `copy_vs_shown < 0.50` — the PRIMARY novelty gate: the piece must NOT transcribe the kb_theory example or
    the classical exemplar it was handed.
  - `copy_vs_corpus < 0.70` — a loose backstop for outright real-song duplicates. GROUNDED: real short
    single-voice excerpts score copy_vs_corpus median 0.39 / p90 0.70 (short diatonic material shares stock
    notes), so the strict from-scratch 0.30 bound does not apply to pedagogical drills.

## Analytics — difficulty grader + training detector (`grade.py`)
- `difficulty_grade(path, key=None)` — a continuous 0-100 score + 1-10 grade from 10 weighted factors (tempo,
  note density, note values, syncopation [meter-aware], rhythmic variety, melodic range+leaps, chromaticism,
  hand-span/polyphony, meter complexity, key-signature accidentals), with the per-factor breakdown and top
  drivers. NO hard beginner/intermediate/advanced cutoff — it's the score; order a lesson set by it, or bucket
  it yourself if you need labels.
- `detect_training(path, key=None)` — auto-labels WHAT the piece trains as keyword tags (meter, tempo, key/
  best-fit scale, syncopation amount, note values present, melodic/textural devices, chord qualities) —
  independent of any requested spec, so you can index/search a library by skill.
- `analyze(path)` returns both. Demo report: `rendered_midi/education/dogfood_batch/ANALYSIS.md` + per-piece
  `*_analysis.json`.

## Honest scope
- The note grammar has no velocity/pedal/articulation field — dynamics & tempo-change concepts are flagged in
  kb_theory as render-layer overlays; the education piece encodes the rhythmic/registral realisation only.
- Theory is common-practice (kb_theory), not corpus-derived; the corpus is used only for optional style
  flavour and the novelty backstop.

## Demo
`compositions/education_demo/` — "syncopation in A harmonic minor (intermediate), + melodic leaps":
single-channel, 0% out-of-scale, syncopation off-beat 0.71, leap max 10 semitones, copy_vs_shown 0.07 /
copy_vs_corpus 0.46 → PASS. Render: `rendered_midi/education/syncopation_a_harmonic_minor_PASS.mid`.
