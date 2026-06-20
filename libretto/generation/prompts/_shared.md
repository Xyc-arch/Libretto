# Grammar format (shared by all tasks)
Header line: `KEY: <tonic mode> | METER: <n/d> | TEMPO: <bpm> | GRID: 16th | BARS: <N>`
Then `VOICES: Name1, Name2, ...` then per-bar blocks:
`@<bar> [<Chord>] (grid:12t)?`  — the `[chord]` bracket is REQUIRED; add `(grid:12t)` ONLY on swung/triplet bars (the `t` suffix is mandatory).
Voice lines (indented): `  <Name>: <Pitch>@<onsetSlot>><durSlots>` ; `+` joins simultaneous notes.
**Slots are 1-INDEXED: slot 1 = the bar's first beat (the downbeat).** In a 16th-note 4/4 grid the four beats fall on slots **1, 5, 9, 13** (beat 2 = slot 5, etc.); a quarter note is `>4`, an eighth `>2`, a sixteenth `>1`. Put on-beat notes on 1/5/9/13 — using 0/4/8/12 makes everything read as OFF-BEAT (maximal syncopation). Slots range 1..16 in a 16th 4/4 bar.
Rules: pitches exact (e.g. `C4`, `F#5`); onset/dur are integer grid slots; keep within [p25,p75] idiomatic band ("mid-band dosage"), avoid extremes; never copy other material.
