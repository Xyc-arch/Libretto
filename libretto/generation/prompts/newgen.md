# newgen — compose a whole piece from scratch (no source)

Compose a complete, full-length piece in a target genre (or a free style/emotion brief). There is
no source and no answer — success is genre-fit + non-degeneracy + genuine novelty + full length.

See `_shared.md` for the grammar format.

Inputs (in CONTEXT):
- `genre`: target genre (or null when `brief` is given).
- `brief`: optional free-text style/emotion brief (then genre-fit is NOT gated).
- `genre_bands`: per-axis idiomatic [p25,p75] target band for the genre (mid-band dosage).
- `kb_excerpts`: cited composing-KB guidance for the idiom.
- `length_bars`: aim within [64,179] bars (full piece).

Requirements:
- Write a complete arrangement (multiple voices, clear sections) of `length_bars`.
- Hit the genre's mid-band on the split axes; classifier-top should land on the target genre.
- Genuinely new: must NOT reproduce any corpus song (anti-copy gated note-level, copy_risk < 0.30).
- Output ONLY the full grammar (header + VOICES + all bars).
