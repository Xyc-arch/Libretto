# SKILL: gaptask — regenerate a held-out region (has ground truth)

Hold out a real region of a real song, regenerate it BLIND, and measure how close it lands to the
held-out truth in the 29-axis space. The only task with an objective external answer.

## Criteria (verdict)
- **Proximity** `D(gen,REAL)` + **beat%** vs chance (89–98% out-of-sample is the validated result).
- **Consistency** `D(ctx,gen)`.
- **Gate**: C1 genre-aware non-degeneracy (≤3 extremes) · C2 length match real ±2 bars ·
  **C3 note-level** (`copy_risk` vs neighbors+corpus low) + **channel-check** (`core.gaptask_channel_check`
  confirms answer-overlap is context-explained reprise, not leakage — verified 100% innocent).

## 4 verbs
1. **setup** — `holdout42_setup.py` (or `gaptask21_setup.py`): pick songs (held-out set is disjoint from
   the corpus — `holdout_select.py`), split into context + held-out region, retrieve k=3 neighbors,
   write per-case briefs (`cases.json`, `<cid>_ctx.txt`, `<cid>_real.txt`).
2. **generate** — feed `prompts/gaptask.md` + each case's context to a `Generator`; the model is BLIND
   to `<cid>_real.txt`. Save `<cid>_gen.txt`.
3. **measure** — `holdout42_measure.py`: fingerprint gen/ctx/real, compute D + beat% + the gate; run
   `python -m libretto.core.gaptask_channel_check <case_dir>` for the integrity split. Writes `measure.json`.
4. **render** — `core.decode_to_midi(grammar, out.mid)` for gen / gen_region / real / real_region.

## Mode: single-shot vs. self-evolving loop (`refine_loop.py`)
The generate step has two modes:
- **single-shot** (default, the powered 42-held-out result): one blind generation, then measure.
- **loop** (`refine_loop.RefinementLoop`, default `max_iter=3`, pick-best): generate → **structural** fitness
  → mid-band dosage corrections → regenerate, up to 3 rounds, keep the lowest-`score` round.

**The loop is LEAKAGE-CLEAN by construction.** Its per-round fitness `refine_loop.region_fitness(region,
ctx, *, genre, target_bars, neighbor_ids)` takes **no** held-out region — it scores only (a) genre-aware
non-degeneracy C1, (b) length vs `target_bars` (the gap SIZE, from the brief, not the answer's content),
(c) context-consistency `D(region,ctx)`, (d) in-band via `core.genre_band_check`, (e) `copy_risk` vs
neighbors+corpus (material the generator could see — never the answer). `dosage_feedback()` is a pure
function of that fitness. Only `final_grade(region, real, ctx, …)` reads the held-out region, and it runs
**after** the loop has already picked its round — so the proximity/beat% number is never loop feedback and
the generator stays blind throughout. (Verify in the wiring: grep `refine_loop.py` — `real` appears only
in `final_grade`.)

Dogfood (6 fresh corpus songs, 2026-06-14, Sonnet generator): single-shot **1/6** gate-pass / mean beat
**96%** (in line with the established ~24% / ~90%). Looping 3 failing cases (max 3 rounds, pick-best) took
**1/3 → pass** and cut the copy overshoot on all three (0.32→0.25, 0.64→0.31, 0.68→0.28) with beat% held at
98–100; the residual failures are non-degeneracy on very short (12-bar) regions, where variation axes pin
near the floor. See `compositions/gaptask_dogfood_20260614/` + `rendered_midi/gaptask/fresh_20260614/`.

## Diagnostics — grounded per-case failure localization (`diagnose.py`)
After grading, `diagnose(region, ctx, *, genre, target_bars, neighbor_ids, real_path=None)` localizes *what is
not good* down to bars and notes — every claim recomputed, none guessed:
- **C1 non-degeneracy** — for each genre-aware extreme axis, leave-one-bar-out attribution: which bars, if
  removed, most move the axis back toward centre (`scope="localized"` → name those bars). An axis pinned too
  LOW is a uniform deficit with no single culprit (`scope="global_deficit"`).
- **C3 / copy** — the single binding source song, the bar-alignment offset, and the exact reused
  `(bar, onset, pitch)` notes grouped by generated bar (catches within-song self-copy too).
- **C2 length** and **replication** (the latter only when `real_path` is passed — the one block that reads
  the held-out answer; mirrors `final_grade`'s leakage boundary).

Returns a structured findings dict; feed it to an agent to write prose *from* the facts (never re-analyze the
grammar). Demo: `paper_data/diagnostics/*.json` (41 dogfood non-passers) + `DOGFOOD_FAILURE_ANALYSIS.md`.

## Reproducibility
measure + render are deterministic (no LLM). Saved demo outputs: repo `compositions/holdout42/`,
`compositions/gaptask21/`, renders in `rendered_midi/gaptask/`. Generation is LLM-stochastic.
Run scripts with `LIBRETTO_DATA=<pkg>/data` (or from the repo root) so corpus/answer-key resolve.
