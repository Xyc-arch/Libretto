---
name: kb_theory
description: A grep-able, index-driven knowledge base of 128 basic music-theory concepts (rhythm, meter, scales/modes, keys, chords, progressions, cadences, melody devices, texture, articulation, dynamics, tempo, form) for an AI that generates SINGLE-CHANNEL PIANO practice pieces for music learners. Every concept entry carries a VALID, renderable Libretto grammar example (single voice `Piano`). This SKILL.md is the INDEX (challenge-dimension → concept entries → file). Concepts live in the topic .txt files. Retrieval is lookup (grep the map → load the entry), not embeddings. Use for the `education` task: browse here for the theory the learner's challenge needs, then optionally retrieve a classical-genre exemplar to flavour the generated practice piece.
---

# kb_theory — index

This is the **index**, not the content. It routes the education task from a *required challenge*
(a rhythm, a key, a scale, a chord, a progression, a melodic device, a texture, an articulation, a tempo, a
form) to the concept entries that teach it. Each entry has: `WHAT` (the theory), `CHALLENGE` (what the
learner practises), and a `GRAMMAR-BEGIN/END` block — a complete, **renderable single-voice piano** Libretto
example. All 128 grammar blocks are verified to parse + render.

## How to retrieve (lookup, not embeddings)
1. Read the learner's required challenge → pick the **challenge dimension(s)** below.
2. Find the matching concept **IDs** in the map, then load each entry from its topic file, e.g.:
   `grep -A20 "ID: TR-SYNCOPATION" kb_theory/rhythm.txt`
3. Compose the practice piece from the retrieved `GRAMMAR` examples + `WHAT`/`CHALLENGE` guidance — single
   voice `Piano`, the difficulty set by which concepts you combine.
4. (Optional, for musical flavour) retrieve a **classical-genre exemplar** via `composing-kb` / the corpus,
   and let it shape register/contour — but keep the output single-channel piano and at the learner's level.

## Education task usage
The education task generates a **single-channel piano** practice score+MIDI with a *required challenge*
(rhythm / melody / key / scale / chord / etc.). Pipeline: **browse kb_theory first** for the concepts the
challenge names → pull their `GRAMMAR` examples as building blocks → optionally retrieve a classical exemplar
for style → assemble a short practice piece at the requested level → render score + MIDI. Difficulty is
controlled by concept selection (e.g. "quarter notes in C major, stepwise" = beginner; "syncopation +
sixteenth runs in D minor with leaps" = intermediate).

## Topic files (128 entries)
| file | entries | covers |
|------|--------|--------|
| `rhythm.txt`      | 25 | note values, rhythm patterns (`TR-PAT-*`), time signatures (`TR-METER-*`) |
| `scales_keys.txt` | 22 | scales & modes (`TS-*`), reference keys (`TS-KEY-*`) |
| `chords.txt`      | 17 | triads, 7ths, extended/sus/power chords, Roman numerals |
| `progressions.txt`| 17 | common progressions (`TP-*`) + cadences (`TP-CAD-*`) |
| `melody.txt`      | 15 | motif, phrase, sequence, contour, non-chord tones (`TM-*`) |
| `texture.txt`     | 10 | mono/homo/poly, arpeggio, Alberti, block/broken, drone (`TX-*`) |
| `expression.txt`  | 14 | articulation (`TE-*`), dynamics, tempo terms |
| `forms.txt`       | 8  | binary, ternary, verse-chorus, 12-bar blues, rondo, etc. (`TF-*`) |

## MAP — by CHALLENGE DIMENSION → concept IDs

### RHYTHM — note values & patterns  (`rhythm.txt`)
note values: TR-WHOLE-NOTE, TR-HALF-NOTE, TR-QUARTER-NOTE, TR-EIGHTH-NOTE, TR-SIXTEENTH-NOTE, TR-DOTTED-NOTE,
  TR-TRIPLET, TR-REST, TR-TIE, TR-SYNCOPATION
patterns: TR-PAT-FOUR-QUARTERS, TR-PAT-HALF-HALF, TR-PAT-QUARTER-TWO-EIGHTHS, TR-PAT-TWO-EIGHTHS-QUARTER,
  TR-PAT-FOUR-EIGHTHS, TR-PAT-DOTTED-LONG-SHORT, TR-PAT-DOTTED-SHORT-LONG, TR-PAT-SIXTEENTH-RUN,
  TR-PAT-TRIPLET-RHYTHM, TR-PAT-SYNCOPATED-RHYTHM

### METER — time signatures  (`rhythm.txt`)
TR-METER-44 (common), TR-METER-34 (waltz), TR-METER-24 (march), TR-METER-68 (compound duple), TR-METER-128 (shuffle)

### KEY & SCALE  (`scales_keys.txt`)
scales/modes: TS-MAJOR-SCALE, TS-NATURAL-MINOR, TS-HARMONIC-MINOR, TS-MELODIC-MINOR, TS-MAJOR-PENTATONIC,
  TS-MINOR-PENTATONIC, TS-BLUES-SCALE, TS-CHROMATIC-SCALE, TS-WHOLE-TONE, TS-DORIAN, TS-PHRYGIAN, TS-LYDIAN,
  TS-MIXOLYDIAN, TS-AEOLIAN, TS-LOCRIAN
keys: TS-KEY-C-MAJOR, TS-KEY-G-MAJOR, TS-KEY-F-MAJOR, TS-KEY-A-MINOR, TS-KEY-E-MINOR, TS-KEY-D-MINOR,
  TS-KEY-BEGINNER-FRIENDLY

### CHORD  (`chords.txt`)
triads: TC-MAJOR-TRIAD, TC-MINOR-TRIAD, TC-DIM-TRIAD, TC-AUG-TRIAD, TC-SUS2, TC-SUS4, TC-POWER-CHORD
sevenths: TC-MAJ7, TC-MIN7, TC-DOM7, TC-HALFDIM7, TC-DIM7
extended: TC-ADD9, TC-SIX, TC-NINE
roman numerals: TC-ROMAN-MAJOR-C, TC-ROMAN-MAJOR-EB

### PROGRESSION & CADENCE  (`progressions.txt`)
progressions: TP-I-V-VI-IV, TP-VI-IV-I-V, TP-I-VI-IV-V, TP-I-IV-V, TP-II-V-I, TP-I-V-IV-I, TP-i-VII-VI-VII,
  TP-i-VI-III-VII, TP-i-iv-V-i, TP-I-bVII-IV-I, TP-I-IV-VI-V; worked: TP-I-V-VI-IV-EB, TP-i-VI-III-VII-CM
cadences: TP-CAD-AUTHENTIC (V–I), TP-CAD-PLAGAL (IV–I), TP-CAD-HALF (ends on V), TP-CAD-DECEPTIVE (V–vi)

### MELODY  (`melody.txt`)
TM-MOTIF, TM-PHRASE, TM-SEQUENCE, TM-STEPWISE, TM-LEAP, TM-CONTOUR, TM-CLIMAX, TM-REPETITION, TM-VARIATION,
TM-CALL-RESPONSE, TM-PASSING-TONE, TM-NEIGHBOR-TONE, TM-APPOGGIATURA, TM-SUSPENSION, TM-RESOLUTION

### TEXTURE  (`texture.txt`)
TX-MONOPHONIC, TX-HOMOPHONIC, TX-POLYPHONIC, TX-UNISON, TX-OCTAVES, TX-ARPEGGIO, TX-ALBERTI-BASS,
TX-BLOCK-CHORDS, TX-BROKEN-CHORDS, TX-DRONE

### ARTICULATION / DYNAMICS / TEMPO  (`expression.txt`)
articulation: TE-STACCATO, TE-LEGATO, TE-TENUTO, TE-ACCENT, TE-SLUR, TE-TIE, TE-FERMATA, TE-GRACE, TE-TRILL,
  TE-MORDENT, TE-TURN
dynamics: TE-DYNAMICS  (loudness markings p/mf/f, crescendo — a render-layer overlay, not in the note grammar)
tempo: TE-TEMPO-TERMS (Largo→Presto ↔ BPM), TE-TEMPO-CHANGE (accel./rit./rubato — overlay)

### FORM  (`forms.txt`)
TF-BINARY (A–B), TF-TERNARY (A–B–A), TF-VERSE-CHORUS, TF-12BAR-BLUES, TF-THEME-VARIATIONS, TF-RONDO,
TF-STROPHIC, TF-THROUGH-COMPOSED

## Honest framing
- **Pedagogical, single-channel piano.** Every example is one `Piano` voice (chords via `+`), so it renders
  to a clean piano score+MIDI a learner can read and play. Difficulty = which concepts you combine.
- **The note grammar has no velocity/pedal/articulation field.** Dynamics (p/f, crescendo) and tempo changes
  (accel./rit./rubato) are flagged in their entries as **performance/render-layer overlays**, not encoded in
  the notes — the GRAMMAR shows the closest rhythmic/registral realisation, honestly labelled.
- **Theory is standard / common-practice**, not corpus-derived (unlike `composing-kb`, which is descriptive of
  the 314-song corpus). For idiomatic *style*, retrieve a classical exemplar from the corpus/composing-kb and
  layer it on top of the theory scaffold.
- All 128 grammar blocks verified to parse + render (single-voice piano).
