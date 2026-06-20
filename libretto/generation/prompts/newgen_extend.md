# newgen_extend — extend/insert into an existing song (no leakage, no answer)

Given a real song, invent a NEW region attached to it: a continuation past the end, a prefix before
the start, or an insertion in the middle. There is no held-out answer — success is coherence to the
source + non-degeneracy + genuine novelty + a connected boundary.

See `_shared.md` for the grammar format.

Inputs (in CONTEXT):
- `source_grammar`: the whole original song.
- `attach`: continuation | prefix | insertion (where the new region goes).
- `neighbor_tendencies`: per-axis hints from the source's k=3 neighbors.
- `length_bars`: 6–40 bars (no length to match).

Requirements:
- COHERE with the source's style (the region should fingerprint near the source on style axes).
- Connect at the seam: share voices (voice-Jaccard ≥ 0.5) and pitch-classes (seam pc Jaccard ≥ 0.10).
- Mid-band dosage; do not chase extremes (except ones the source itself idiomatically has).
- Genuinely new: copy_risk < 0.30 vs the source AND the corpus (don't parrot the source).
- An insertion may legitimately contrast (bridge) — still must stay closer to the source than chance.
- Output ONLY the new region's bars.
