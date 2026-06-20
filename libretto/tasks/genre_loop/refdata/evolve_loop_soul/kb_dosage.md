# KB dosage layer — evolving refinement to composing-kb concept IDs
# Fitness target: land each axis in the idiomatic BAND (25th–75th pct), NOT the corpus mean.
# Only OUT-OF-BAND axes get new dosage rules. In-band axes are left alone.
# SCOPE: this refines toward IDIOMATIC STRUCTURE (typicality), NOT toward "better music".

## Round 0 (baseline)
(no dosage guidance — compose from composing-kb as-is)

## Round 2 dosage (targets Round-1 EXTREMES: syncopation 100, dur_cv/mean_dur/density 0, max_chord_width 2)
- **R-SYNCO [adjust dosage]**: target the corpus syncopation BAND (~45–65th pct), NOT the maximum.
  Anchor most downbeats (slots 1/5/9/13 sound on-beat); place off-beat accents on ~half the onsets,
  not all. (Round 1 put nearly every onset off-beat → 100th pct overshoot.)
- **R-DURVAR [new dosage]**: do NOT make every note one slot. Sustain chords/pads (half/whole notes,
  8–16 slots) under shorter melodic figures (1–4 slots); mix long & short so duration VARIES.
  (fixes dur_cv=0 and mean_dur=0.)
- **R-DYNAMICS [new dosage]**: vary bar density — sparser verse bars vs busier fill/turnaround bars,
  so per-bar note counts differ rather than every bar identical. (fixes density_variability=0.)
- **V-WIDE [adjust dosage]**: open the voicing — bass an octave+ below the chord, chordal/pad voice
  spread across >1 octave (root + mid + top) so simultaneous spans exceed ~13 semitones on hits.
  (fixes max_chord_width=2.) Add a sustained Pad/Strings voice (also raises voice_count).

## Round 3 dosage (corrects Round-2 OVERSHOOTS: syncopation 0, mean_dur 97, onset_pos_entropy 2, root_motion 96)
- **R-SYNCO [re-balance]**: "target band" means ~40–55% of onsets off-beat — Round 2 anchored ALL
  onsets on-beat (0th pct). Restore backbeat & off-beat accents (chord stabs on slots 2/4/6/8/12/14,
  bass push-notes) so syncopation sits mid-band, not at either extreme.
- **R-DURVAR [re-balance]**: Round 2 over-sustained (pads = whole notes on every bar → mean_dur 97th).
  Keep SOME sustain but add quarter/eighth motion; don't let every voice hold whole notes. Aim for a
  mix, not wall-to-wall pads.
- **R-ONSETSPREAD [new dosage]**: spread onsets across many in-bar positions (not only slots 1/5/9/13)
  — varied subdivisions raise onset-position variety to mid-band (fixes onset_pos_entropy=2).
- **H-ROOTVAR [new dosage]**: do NOT cycle a brand-new bass root every bar through maximally varied
  intervals (root_motion_entropy ~96–98th). Repeat roots, use pedal/stepwise bass on some bars, so
  root-motion variety lands mid-band.

## Round 4 dosage (corrects Round-3 NEW extremes: distinct_bar_frac 100, fourth_motion 99; + plain-harmony drift)
- **F-REPRISE [adjust dosage]**: REUSE material — Round 3 made every bar unique (distinct_bar_frac
  100th). Repeat a 2-bar verse riff verbatim so the distinct-bar fraction sits mid-band (~70–85);
  literal repetition is idiomatic, not lazy.
- **H-FOURTHS [re-balance]**: do NOT resolve up-a-fourth on every change (fourth_motion 99th). Mix in
  third-motion (F→Am), stepwise (F→Eb bVII), and descending roots so up-a-fourth is one device among
  several (mid-band).
- **H-COLOR [new dosage]**: enrich harmony — use maj7/m7/9th chords, a chromatic passing chord
  (e.g. Bbm6, Eb bVII), and CHANGE chords within the bar sometimes (half-bar changes). Raises
  harmonic vocabulary / chromaticism / distinct-pc / chord-change-rate toward band (Round 3 left
  them at 5–8th pct).
- **R-DYNAMICS [reinforce]**: keep bar-density contrast (sparse repeated-riff verse bars vs busier
  B-section/fills) — Round 3 evened out to density_variability=6.
