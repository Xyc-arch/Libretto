# Jazz self-evolving loop — jazz-conditioned band target, full length, feedback-driven

Fixes vs the prior one-shot jazz a/b (which was COMPROMISED: 7 extremes, 36 bars, classified latin 46%):
full length (~64 bars), feedback-driven dosage, and target = the JAZZ MID-BAND (not the ceiling).
Jazz-discriminating axes (chromaticism, dimaug_rate, triplet_share, distinct_pc, interval_entropy)
scored vs jazz-conditioned p25-p75; all others vs global band. Out-of-band on a jazz axis = either
direction (undershoot OR overshoot). Honest: target is the BAND middle, not the ceiling; typicality not quality.

## Round-by-round trajectory
| round | jazz axes in-band | degenerate extremes (excl. jazz-idiomatic) | out-of-band | key dosage change applied next |
|---|---|---|---|---|
| r1 | 4/5 (triplet HIGH 0.61) | 3 real (syncopation 2, dur_cv 4, density_var 4) + 2 jazz-idiomatic* | 18 | raise syncopation, vary dur/density, slow harmonic rhythm, trim triplet, +voice, widen melody |
| r2 | **5/5** (triplet 0.55, syncopation 2→58) | 2 (density_var 5, distinct_bar 100 overshoot) + distinct_pc* | 12 | reuse sections (distinct_bar overshot), slow vocab, more stepwise melody |
| r3 | 4/5 (interval_entropy fell 0.62 LOW) | 0 + distinct_pc* | 9 | restore interval variety (melody went too stepwise) |
| r4 | **5/5** (interval_entropy 0.83; step_ratio fell 0.15 LOW) | 0 + distinct_pc* | 7 | balance melody step/leap to ~half/half |
| r5 | **5/5** (step_ratio & range fixed; all 5 in) | 0 + distinct_pc* | 7 | — FINAL |
*distinct_pc=12 (all 12 pcs) and fourth_motion-high (ii-V-I engine) are JAZZ-IDIOMATIC, not degeneracy.

The dosage lesson, applied to genre-targeting: the loop repeatedly caught OVERSHOOT and pulled toward
mid-band — triplet 0.61→0.55 (never 1.0), distinct_bar 100→42 (reuse restored), and the melody
step/leap pair oscillated (r3 too stepwise → r4 too leapy → r5 balanced) before settling. The 5
jazz-discriminating axes converged into the jazz band by r2 and held (with the r3 interval_entropy dip
fixed by r4). Remaining genre-neutral residuals (vocab_density, fourth_motion high; novelty high;
section count low) are jazz-INHERENT — rich jazz harmony and head/solo form genuinely exceed the
pop-dominated global median; pulling them "in" would de-jazz the piece.

## Final gated + classified result (jazzloop/r5.txt, 64 bars)
- **Jazz band: 5/5 jazz axes IN** — chromaticism 0.10, dimaug 0.39, triplet 0.55, distinct_pc 12, interval_entropy 0.78.
- **C1 no-degenerate-extremes: PASS** — 1 extreme (distinct_pc=12, jazz-idiomatic), well under threshold; none of the song_0014-style mechanical extremes.
- **C2 length: PASS** — 64 bars (corpus p10).
- **C3 replication: PASS** — 0% exact bar copies, 0% verbatim 8-bar progressions, 0 copies of KB-cited bars (mel 6-gram overlap 3%). Genuine composition, not retrieval.
- **Genre classifier: jazz 56% (TOP), classical 21% (jazz+classical complex = 77%), latin 6%.** Classifies cleanly toward jazz — NOT latin (the one-shot overshoot landed latin 46%), NOT degenerate.

## VERDICT: PASS
Lands in the jazz band on all 5 jazz axes, passes all 3 validity gates, and classifies toward jazz
(56% top / 77% jazz-classical-complex, latin only 6%). The full-length, feedback-driven, mid-band loop
fixed every issue that compromised the one-shot jazz a/b (degeneracy, sub-length, latin mis-classification).
Demonstrates the architecture supports genre-targeted self-refinement — typicality, not quality; n=1.
