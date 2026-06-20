# SKILL: genre_loop — the self-evolving composition loop (genre-adaptive)

Compose toward a target genre (or the global idiomatic band) by **feedback-driven self-refinement**:
generate → fingerprint vs the target band → let the out-of-band axes drive a dosage adjustment toward
mid-band → recompose → repeat until convergence. This is the loop the rest of the project's dosage
discipline came from ("aim the band MIDDLE, not the ceiling — overshoot is as wrong as undershoot").

## The per-round procedure
1. **setup** — choose `genre` (one of `core.genre_band_check.genres()`) or `None` for the global band.
   Build the round-1 dosage targets: each of the 8 genre-discriminating SPLIT axes aims at the genre's
   **p50**, staying inside the genre band **[p25,p75]**; every other axis aims inside the **global
   [p25,p75]** band. Compose round 1 from the composing-KB under those targets.
2. **measure each round** — `core.genre_band_check.check(piece, genre, prev=<prev_round>.json,
   save=<this_round>.json)`. It reports, adaptively for the chosen genre:
   - per split axis: value vs the genre band, `LOW` / `in` / `HIGH` (out-of-band in EITHER direction),
   - genre-neutral axes outside the global band,
   - degenerate global extremes (≤5 / ≥95 pct), profile spread (mean-collapse guard), and DRIFT vs prev.
   It is **genre-adaptive, not hardcoded**: a pinned genre band (e.g. jazz `distinct_pc` p25=p75=12)
   widens to that genre's data-driven [p5,p95] — no per-genre exceptions in the code.
3. **adjust dosage** — for each out-of-band axis move TOWARD its p50: `LOW` → increase that trait,
   `HIGH` → reduce it (trim the overshoot). Preserve spread (don't collapse everything to the mean).
   Re-brief the generator with the corrections and recompose.
4. **convergence / stop** — stop when the split axes are all in-band, degenerate extremes are only
   genre-idiomatic ones, the out-of-band set stabilizes round-to-round, AND profile spread is retained
   (no mediocrity-trap collapse). Then **gate** the final with the validity gate + `core.copy_risk`.

## Engines (in core/, deterministic)
- `core.genre_band_check` — the genre-ADAPTIVE per-round check above (`check`, `genre_band`, `genres`).
- `core.band_profile` / `core.band_status` (`band_check`) — the GLOBAL-band profile + drift verdict
  (toward-band / away / centering, mediocrity-trap), usable for a genre-agnostic loop.
- band-targeting in code also lives in `tasks/newgen/newgen_setup.py::gband()` (genre p25/p50/p75).

## Canonical reference data (round-by-round, shipped)
- `refdata/jazzloop/` — the **jazz** genre-conditioned loop, 5 rounds: `r1..r5.txt` (compositions) +
  `r1..r5.json` (per-round global-percentile profiles) + `JAZZLOOP_RESULTS.md` (trajectory: jazz axes
  converge by r2; the melody step/leap pair oscillates r3→r5 then settles; triplet 0.61→0.55, never 1.0).
- `refdata/evolve_loop_soul/` — the **original** soul-groove loop: `round1..N` + `drift_log.md`,
  `kb_dosage.md`, `genre_corroboration.md` (where the mid-band dosage lesson was first established).

## Reproducibility
The per-round CHECK and the profiles are deterministic. The COMPOSITION each round is LLM-driven
(stochastic) — the shipped rounds are the canonical demonstration, not a reproducible transcript.
Generation brief template: `generation/prompts/newgen.md` (genre mode) + the corrections from step 3.
Honest scope: "more genre-idiomatic" = typicality, NOT quality.
