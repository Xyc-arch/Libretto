# composing-kb structural audit — PROPOSED changes (not applied; for review)

Part 1 (re-grounding on 314) is already applied. The below are structural proposals — decide which
to apply. Scope-honest: descriptive/idiomatic, not quality; no invented (ungrounded) patterns.

## P1 — Coverage gaps: ~16 of 28 axes have NO concept (the loop can't steer them via the KB)
Axis → concept map shows these 28-axis dimensions have **no KB concept addressing them**, so the
self-evolving loop had to INVENT ad-hoc dosage (R-DURVAR, R-DYNAMICS, R-ONSETSPREAD, H-COLOR,
H-ROOTVAR in `evolve_loop/kb_dosage.md`) for exactly these:
- rhythm: `onset_density_per_bar`, `onset_pos_entropy`, `dur_cv`, `mean_dur_beats`, `density_variability`
- harmony: `chord_change_rate` (harmonic rhythm — notable absence), `vocab_density`, `distinct_pc`, `pc_entropy`
- melody: `pitch_range`, `voice_range`, `interval_entropy`, `up_ratio`
- texture: `active_voice_density`
- form: `novelty_rate`, `section_per100bars` (sectional contrast / how many sections)
**Proposal:** add ~6 grounded concepts (each needs a detector in `pattern_catalog.py`, computed from
the corpus — not invented):
- `R-DURVAR` (duration variety) → dur_cv, mean_dur · `R-DENSITY` (density & ebb/flow) →
  onset_density, density_variability, active_voice_density · `R-RHYTHMVAR` (onset-position variety)
  → onset_pos_entropy · `H-RHYTHM` (harmonic rhythm / chord-change rate) → chord_change_rate,
  vocab_density · `H-PALETTE` (pitch-class palette breadth) → distinct_pc, pc_entropy ·
  `M-RANGE` (melodic range & contour) → pitch_range, voice_range, interval_entropy, up_ratio ·
  `F-SECTIONS` (sectional form / contrast) → novelty_rate, section_per100bars.
  This would let the loop's invented dosage rules become first-class, grounded KB concepts.

## P1 — Stale axis reference: V-DOUBLE measures a DROPPED axis
`V-DOUBLE` (unison/octave doubling, attested 173/314) is a valid pattern, but the corresponding
fingerprint axis `tex_doubling_ratio` was **dropped** in the 28-axis revision (it went degenerate on
the diverse corpus). So the loop can *attest* V-DOUBLE but cannot *steer* it (no axis to measure).
**Decision needed:** (a) re-add a doubling axis to the 28-axis system, or (b) mark V-DOUBLE
"attestation-only, not loop-steerable" on the entry. (No code references doubling_ratio in band_check;
the mismatch is conceptual, not a broken reference.)

## P2 — Examples are pop-only; genre-specific patterns cite the wrong genre
Every cited EXAMPLE is `song_0001–0027` (the original pop set). The re-grounding shows several
patterns are now genre-specific and most-attested OUTSIDE pop — but their examples don't reflect it:
- `M-SIGH` — classical 93% (vs pop ~68%) but cites Stevie Wonder/Beatles; should add a classical example.
- `M-GAPFILL` — jazz 93%; should cite a jazz example.
- `H-AUG` — classical 83% / jazz 79% (folk 12%); should cite a classical/jazz example.
- `R-OSTINATO` — electronic/film high (jazz 32%); add an electronic example.
**Proposal:** add 1 cross-genre EXAMPLE per genre-specific concept (cite real tokens from the new
314, e.g. a Chopin/Bach `song_01xx` for M-SIGH). Keeps examples honest to the multi-genre attestation.

## P3 — Stale prose stats in WHAT text (minor)
Re-grounding rewrote STATUS/ATTEST lines but not WHAT prose. A few hardcoded 59-song stats are now
slightly off: R-SYNCO "every song shows ≥15%" (now 311/314), R-STRAIGHT "~83% of songs" (now 86%).
**Proposal:** refresh these few numbers to the 314 figures (or soften to "nearly all / most").

## P3 — Modularity / index routing (optional, low value)
- Modularity is otherwise clean — no real duplication. Optional: group the three chromatic-color
  sonorities (H-DIM, H-AUG, H-DOM7) under one cross-ref heading; they're musically distinct, so I'd
  **keep them separate** (merging would lose the dom7-vs-dim-vs-aug distinction the loop uses).
- MAP 3 (by task) has no row for "set harmonic rhythm" / "set density / arrangement thickness" /
  "build sectional contrast" — add those rows IF the P1 concepts are created.

## Not an issue (audited, no change)
- **Generative quality: all 22 COMPOSE notes are actionable** ("Put a bass note on @1,@5,@9,@13",
  "raise its 5th a semitone for one beat", "Invent ONE small interval shape…") — produce-this, not
  recognize-this. No fixes needed.
- **Coherence definition↔example↔compose**: consistent within each entry; no contradictions found.
- **Index routing** reaches all 22 concepts via the 4 maps; the only routing gaps are the uncovered
  axes (P1), which have nothing to route to yet.
