---
name: kb_theory
description: A grep-able, index-driven knowledge base of 193 basic music-theory concepts (rhythm, meter, scales/modes, keys, chords, progressions, cadences, melody devices, texture, articulation, dynamics, tempo, form) for an AI that generates SINGLE-CHANNEL PIANO practice pieces for music learners. Every concept entry carries a VALID, renderable Libretto grammar example (single voice `Piano`). This SKILL.md is the INDEX (challenge-dimension → concept entries → file). Concepts live in the topic .txt files. Retrieval is lookup (grep the map → load the entry), not embeddings. Use for the `education` task: browse here for the theory the learner's challenge needs, then optionally retrieve a classical-genre exemplar to flavour the generated practice piece.
---

# kb_theory — index

This is the **index**, not the content. It routes the education task from a *required challenge*
(a rhythm, a key, a scale, a chord, a progression, a melodic device, a texture, an articulation, a tempo, a
form) to the concept entries that teach it. Each entry has: `WHAT` (the theory), `CHALLENGE` (what the
learner practises), and a `GRAMMAR-BEGIN/END` block — a complete, **renderable single-voice piano** Libretto
example. All 193 grammar blocks are verified to parse + render.

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

## Topic files (193 entries)
| file | entries | covers |
|------|--------|--------|
| `rhythm.txt`      | 34 | note values, rhythm patterns (`TR-PAT-*`), swing/hemiola/anacrusis/polyrhythm, time signatures (`TR-METER-*`, incl. 3/8·5/4·7/8·9/8) |
| `scales_keys.txt` | 34 | scales & modes (`TS-*`, incl. octatonic/altered/bebop/lydian-dominant/phrygian-dominant/harmonic-major), reference keys (`TS-KEY-*`) |
| `chords.txt`      | 26 | triads, 7ths, extended (9/11/13), altered dom, sus/power, inversions, secondary dom, Neapolitan, aug-6th, quartal, Roman numerals |
| `progressions.txt`| 24 | common progressions (`TP-*`), circle-of-fifths/turnaround/Andalusian/Pachelbel/tritone-sub + cadences (`TP-CAD-*`) |
| `melody.txt`      | 24 | motif, phrase, period, sequence, inversion/retrograde/augmentation/diminution, contour, non-chord tones, ostinato (`TM-*`) |
| `texture.txt`     | 17 | mono/homo/poly, arpeggio, Alberti, block/broken, drone, walking bass, ostinato, pedal point, countermelody, canon, stride (`TX-*`) |
| `expression.txt`  | 20 | articulation (`TE-*`), dynamics, tempo terms, pedal/roll/gliss/portato |
| `forms.txt`       | 14 | binary, ternary, verse-chorus, 12-bar blues, rondo, AABA, sonata, minuet-trio, ground bass, arch, pop sections (`TF-*`) |

## MAP — by CHALLENGE DIMENSION → concept IDs

### RHYTHM — note values & patterns  (`rhythm.txt`)
note values: TR-WHOLE-NOTE, TR-HALF-NOTE, TR-QUARTER-NOTE, TR-EIGHTH-NOTE, TR-SIXTEENTH-NOTE, TR-DOTTED-NOTE,
  TR-TRIPLET, TR-REST, TR-TIE, TR-SYNCOPATION
patterns: TR-PAT-FOUR-QUARTERS, TR-PAT-HALF-HALF, TR-PAT-QUARTER-TWO-EIGHTHS, TR-PAT-TWO-EIGHTHS-QUARTER,
  TR-PAT-FOUR-EIGHTHS, TR-PAT-DOTTED-LONG-SHORT, TR-PAT-DOTTED-SHORT-LONG, TR-PAT-DOTTED-EIGHTH-SIXTEENTH,
  TR-PAT-SIXTEENTH-RUN, TR-PAT-TRIPLET-RHYTHM, TR-PAT-SYNCOPATED-RHYTHM
feel & advanced: TR-ANACRUSIS (pickup), TR-HEMIOLA, TR-SWING, TR-POLYRHYTHM-3-2

### METER — time signatures  (`rhythm.txt`)
TR-METER-44 (common), TR-METER-34 (waltz), TR-METER-24 (march), TR-METER-68 (compound duple), TR-METER-128 (shuffle),
TR-METER-38, TR-METER-54, TR-METER-78 (2+2+3), TR-METER-98 (compound triple)

### KEY & SCALE  (`scales_keys.txt`)
scales/modes: TS-MAJOR-SCALE, TS-NATURAL-MINOR, TS-HARMONIC-MINOR, TS-MELODIC-MINOR, TS-MAJOR-PENTATONIC,
  TS-MINOR-PENTATONIC, TS-BLUES-SCALE, TS-CHROMATIC-SCALE, TS-WHOLE-TONE, TS-DORIAN, TS-PHRYGIAN, TS-LYDIAN,
  TS-MIXOLYDIAN, TS-AEOLIAN, TS-LOCRIAN, TS-OCTATONIC, TS-LYDIAN-DOMINANT, TS-ALTERED, TS-PHRYGIAN-DOMINANT,
  TS-HARMONIC-MAJOR, TS-BEBOP-DOMINANT
keys: TS-KEY-C-MAJOR, TS-KEY-G-MAJOR, TS-KEY-D-MAJOR, TS-KEY-A-MAJOR, TS-KEY-E-MAJOR, TS-KEY-F-MAJOR,
  TS-KEY-BB-MAJOR, TS-KEY-EB-MAJOR, TS-KEY-A-MINOR, TS-KEY-E-MINOR, TS-KEY-D-MINOR, TS-KEY-BEGINNER-FRIENDLY,
  TS-RELATIVE-KEYS (relative major/minor)

### CHORD  (`chords.txt`)
triads: TC-MAJOR-TRIAD, TC-MINOR-TRIAD, TC-DIM-TRIAD, TC-AUG-TRIAD, TC-SUS2, TC-SUS4, TC-POWER-CHORD, TC-QUARTAL
sevenths: TC-MAJ7, TC-MIN7, TC-DOM7, TC-HALFDIM7, TC-DIM7, TC-MINMAJ7
extended / altered: TC-ADD9, TC-SIX, TC-NINE, TC-DOM11, TC-DOM13, TC-DOM7B9
inversions & functional: TC-INVERSIONS (root/1st/2nd), TC-SECONDARY-DOM (V7/V), TC-NEAPOLITAN (bII), TC-AUG-SIXTH (It/Ger)
roman numerals: TC-ROMAN-MAJOR-C, TC-ROMAN-MAJOR-EB

### PROGRESSION & CADENCE  (`progressions.txt`)
progressions: TP-I-V-VI-IV, TP-VI-IV-I-V, TP-I-VI-IV-V, TP-I-IV-V, TP-II-V-I, TP-I-V-IV-I, TP-i-VII-VI-VII,
  TP-i-VI-III-VII, TP-i-iv-V-i, TP-I-bVII-IV-I, TP-I-IV-VI-V, TP-CIRCLE-OF-FIFTHS, TP-TURNAROUND (I–vi–ii–V),
  TP-ANDALUSIAN (i–bVII–bVI–V), TP-PACHELBEL, TP-SECONDARY-DOM (V7/V), TP-TRITONE-SUB; worked: TP-I-V-VI-IV-EB, TP-i-VI-III-VII-CM
cadences: TP-CAD-AUTHENTIC (V–I), TP-CAD-PLAGAL (IV–I), TP-CAD-HALF (ends on V), TP-CAD-DECEPTIVE (V–vi), TP-CAD-PICARDY (minor→major I)

### MELODY  (`melody.txt`)
TM-MOTIF, TM-PHRASE, TM-PERIOD (antecedent/consequent), TM-SEQUENCE, TM-STEPWISE, TM-LEAP, TM-CONTOUR, TM-CLIMAX,
TM-REPETITION, TM-VARIATION, TM-INVERSION, TM-RETROGRADE, TM-AUGMENTATION, TM-DIMINUTION, TM-OSTINATO,
TM-CALL-RESPONSE, TM-PASSING-TONE, TM-NEIGHBOR-TONE, TM-APPOGGIATURA, TM-SUSPENSION, TM-RESOLUTION,
TM-ANTICIPATION, TM-ESCAPE-TONE, TM-PEDAL-TONE

### TEXTURE  (`texture.txt`)
TX-MONOPHONIC, TX-HOMOPHONIC, TX-POLYPHONIC, TX-UNISON, TX-OCTAVES, TX-ARPEGGIO, TX-ALBERTI-BASS,
TX-BLOCK-CHORDS, TX-BROKEN-CHORDS, TX-DRONE, TX-WALKING-BASS, TX-OSTINATO, TX-PEDAL-POINT, TX-COUNTERMELODY,
TX-CALL-RESPONSE, TX-CANON, TX-STRIDE

### ARTICULATION / DYNAMICS / TEMPO  (`expression.txt`)
articulation: TE-STACCATO, TE-LEGATO, TE-TENUTO, TE-ACCENT, TE-MARCATO, TE-SFORZANDO, TE-PORTATO, TE-SLUR,
  TE-TIE, TE-FERMATA, TE-GRACE, TE-TRILL, TE-MORDENT, TE-TURN, TE-ARPEGGIO-ROLL, TE-GLISSANDO, TE-SUSTAIN-PEDAL
dynamics: TE-DYNAMICS  (loudness markings p/mf/f, crescendo — a render-layer overlay, not in the note grammar)
tempo: TE-TEMPO-TERMS (Largo→Presto ↔ BPM), TE-TEMPO-CHANGE (accel./rit./rubato — overlay)

### FORM  (`forms.txt`)
TF-BINARY (A–B), TF-TERNARY (A–B–A), TF-VERSE-CHORUS, TF-12BAR-BLUES, TF-THEME-VARIATIONS, TF-RONDO,
TF-STROPHIC, TF-THROUGH-COMPOSED, TF-AABA (32-bar), TF-SONATA, TF-MINUET-TRIO, TF-GROUND-BASS, TF-ARCH,
TF-POP-SECTIONS (intro/verse/chorus/bridge)

## Honest framing
- **Pedagogical, single-channel piano.** Every example is one `Piano` voice (chords via `+`), so it renders
  to a clean piano score+MIDI a learner can read and play. Difficulty = which concepts you combine.
- **The note grammar has no velocity/pedal/articulation field.** Dynamics (p/f, crescendo) and tempo changes
  (accel./rit./rubato) are flagged in their entries as **performance/render-layer overlays**, not encoded in
  the notes — the GRAMMAR shows the closest rhythmic/registral realisation, honestly labelled.
- **Theory is standard / common-practice**, not corpus-derived (unlike `composing-kb`, which is descriptive of
  the 314-song corpus). For idiomatic *style*, retrieve a classical exemplar from the corpus/composing-kb and
  layer it on top of the theory scaffold.
- All 193 grammar blocks verified to parse + render (single-voice piano).
