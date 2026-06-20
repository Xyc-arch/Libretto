# gaptask — regenerate a held-out region (you are BLIND to the real answer)

You are given a song's CONTEXT (the bars surrounding a removed region) and the structural
tendencies of its k=3 nearest corpus neighbors (IDs + axis tendencies only — never their notes).
Generate the MISSING region so it reads as a natural part of THIS song.

See `_shared.md` for the grammar format.

Inputs (in CONTEXT):
- `context_grammar`: the visible bars (before and/or after the gap).
- `gap_type`: one of start | infill | continuation (where the region sits).
- `target_bars`: how many bars to generate (match this — success is gated on length ±2 bars).
- `neighbor_tendencies`: per-axis "aim higher/lower/typical" hints from the 3 neighbors.
- `key`, `meter`, `tempo`: carry from the context.

Requirements:
- Continue the song's established material at the seam (shared voices, compatible harmony).
- Mid-band dosage: aim for the idiomatic [p25,p75] band on each axis; do NOT chase extremes.
- Do NOT reproduce the neighbors' or any other song's material (anti-copy is gated, note-level).
- Output ONLY the generated region's bars (same voice names as context), length ≈ target_bars.
