# Self-evolving composition loop — drift trajectory

Fitness = land in the idiomatic BAND (25–75th pct), NOT the mean. Only out-of-band axes drove KB
dosage edits. SCOPE: refines toward IDIOMATIC STRUCTURE (typicality), NOT "better music".

## Headline per round
| metric | R1 | R2 | R3 | R4 |
|---|---|---|---|---|
| in-band | 9 | 13 | 15 | 16 |
| out-band | 19 | 15 | 13 | 12 |
| EXTREME | 7 | 4 | 2 | 0 |
| spread(sd) | 34.6 | 30.0 | 31.1 | 25.9 |
| near-mean[40-60] | 6 | 5 | 4 | 9 |

## Per-axis percentile trajectory (R1→R2→R3→R4)
| axis | R1 | R2 | R3 | R4 | final band |
|---|---|---|---|---|---|
| `rhy_syncopation_rate` | 100 | 0 | 71 | 51 | in-band |
| `rhy_onset_density_per_bar` | 44 | 13 | 24 | 23 | mild-out |
| `rhy_triplet_share` | 16 | 16 | 16 | 16 | mild-out |
| `rhy_onset_pos_entropy` | 69 | 2 | 86 | 68 | in-band |
| `rhy_dur_cv` | 0 | 25 | 87 | 85 | mild-out |
| `rhy_mean_dur_beats` | 0 | 97 | 29 | 57 | in-band |
| `rhy_density_variability` | 0 | 20 | 6 | 11 | mild-out |
| `har_chromaticism` | 46 | 15 | 5 | 53 | in-band |
| `har_distinct_pc` | 17 | 17 | 7 | 54 | in-band |
| `har_pc_entropy` | 91 | 82 | 93 | 47 | in-band |
| `har_chord_change_rate` | 4 | 8 | 8 | 32 | in-band |
| `har_vocab_density` | 41 | 78 | 75 | 95 | mild-out |
| `har_root_motion_entropy` | 98 | 96 | 69 | 95 | mild-out |
| `har_fourth_motion_rate` | 78 | 89 | 99 | 89 | mild-out |
| `har_dimaug_rate` | 86 | 50 | 59 | 66 | in-band |
| `mel_pitch_range` | 8 | 12 | 8 | 13 | mild-out |
| `mel_step_ratio` | 7 | 21 | 29 | 15 | mild-out |
| `mel_interval_entropy` | 94 | 54 | 71 | 83 | mild-out |
| `mel_up_ratio` | 46 | 55 | 44 | 80 | mild-out |
| `mel_voice_range` | 34 | 48 | 34 | 50 | in-band |
| `tex_voice_count` | 18 | 25 | 25 | 25 | in-band |
| `tex_mean_simultaneity` | 57 | 75 | 68 | 71 | in-band |
| `tex_max_chord_width` | 2 | 68 | 50 | 69 | in-band |
| `tex_active_voice_density` | 40 | 54 | 35 | 40 | in-band |
| `form_self_similarity` | 92 | 64 | 45 | 42 | in-band |
| `form_novelty_rate` | 78 | 75 | 91 | 84 | mild-out |
| `form_distinct_bar_frac` | 11 | 61 | 100 | 46 | in-band |
| `form_section_per100bars` | 26 | 26 | 26 | 26 | in-band |

## Verdict (4 rounds)

**Compositions moved into-band over rounds — the core claim holds.** EXTREME axes (<5/>95) fell
monotonically **7 → 4 → 2 → 0**; in-band (25–75) rose **9 → 13 → 15 → 16**. By Round 4 the piece had
zero extreme axes vs the 314-song corpus, starting from a Round-1 piece with 7.

**KB changes were sensible DOSAGE fixes, not metric-gaming.** Each round's edit was a musical
instruction tied to the specific out-of-band axis: "target the syncopation band, not the maximum";
"mix note durations, don't make every note one slot"; "open the voicing past an octave"; "repeat a
verse riff verbatim"; "mix root motion, don't cadence up-a-fourth every bar"; "add maj7/9th/chromatic
color and half-bar changes." The tell that this was real composing and NOT direct number-targeting:
axes **oscillated then converged** — syncopation 100→0→71→51, mean_dur 0→97→29→57, dur_cv 0→25→87→85.
A metric-gamer hits the band on the first try; a composer applying dosage guidance overshoots and
settles. That oscillation is the honest signature.

**Mediocrity-trap watch (the crucial honesty).**
- R1→R2 and R2→R3: spread stayed healthy (34.6→30→31) and the near-mean[40–60] cluster stayed FLAT
  (6→5→4). The spread dip was extremes ENTERING the band, not homogenization — good.
- R3→R4: spread fell to **25.9** (just under the real-song norm ~27) AND near-mean jumped **4→9**.
  This is the FIRST genuine centering signal — the early edge of the trap. **We stop here**: extremes
  are already eliminated, and another round of band-chasing would start collapsing variance toward the
  bland center for diminishing returns.

**Honest limits.**
- Scope: the fitness signal is **typicality, not quality**. "More idiomatic" ≠ "better music."
- A few axes are PINNED by hand-composition choices, not the loop: `rhy_triplet_share` stuck at 16
  (I wrote only binary 16th-grid rhythms — no triplets), `form_section_per100bars` stuck at 26 and
  `rhy_onset_density` ~23 (fixed 16-bar length). These need a triplet/longer-form composition to move,
  not a KB dosage edit.
- 12 axes remain mild-out-of-band (no extremes) after 4 rounds — reducing those further is exactly
  what risks the mean-collapse flagged above, so they were left.
