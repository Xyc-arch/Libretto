# SKILL: newgen — compose a whole piece from scratch (no source)

Compose a full-length piece in a target genre (or a free style/emotion brief). No source, no answer.

## Criteria (verdict) — ADAPTIVE, genre-calibrated (`calibrate.py`)
- **C2 length** ∈ [64,179] bars.
- **non-degenerate** — genre-aware C1 extremes ≤ `c1_budget(genre)`.
- **genuinely-new** — `copy_risk` (note-level vs corpus) < `copy_threshold(genre)`.
- **genre-fit** — classifier-top == target OR split-axes-in-band ≥ `fit_threshold(genre)`. *(brief: not gated.)*

All three thresholds are **derived from real corpus songs of the genre**, not fixed. The old fixed `C1 ≤3` /
`fit ≥6/8` rejected the ground truth (only ~20% of real songs reach fit ≥6/8 — the binomial tail; film_score
real-song C1 pass was 20%). Calibrated thresholds admit ~85% of real songs (e.g. latin C1 budget 5,
jazz/classical/film/electronic 6, pop/funk 4; band-fit floor 3 with the classifier as the primary genre
test). **Copy is also adaptive**: `copy_threshold(genre)` = the genre's real-song copy ceiling (MAX of
copy_risk vs corpus, self-excluded) × 1.20 headroom, rounded, floored at the 0.30 standard (never stricter),
capped at 0.45 — idiom-heavy genres (latin montuno, etc.) legitimately reuse more, so the gate tracks the
genre's most-reusing real song (e.g. latin 0.34). The 0.45 CAP guards against a near-duplicate pair inflating
a genre's gate (the pop U2 0048/0110 dupe). Recompute: `python3 -m libretto.tasks.newgen.calibrate` →
`data/newgen_calibration.json`. (Base statistic = `COPY_PCTL`; 1.0=max, lower for a robust percentile.)

## 4 verbs
1. **setup** — `newgen_setup.py`: build the prompt with **MANDATORY retrieval** (`retrieval.py`): the genre's
   KB concepts (EXAMPLE + COMPOSE, via composing-kb MAP 1) + the most prototypical real corpus exemplars
   (nearest the genre fingerprint centroid). Blind dosage numbers don't teach an idiom; examples do — and an
   A/B showed they HALVE copy_risk (0.33→0.12) and lift genre-fit. Setup raises if a genre is unmapped.
2. **generate** — feed `prompts/newgen.md` + context to a `Generator`. Save `<id>_gen.txt`.
3. **measure** — `newgen_measure.py`: fingerprint, genre-aware C1, `copy_risk` vs corpus, and a
   scikit-learn LogReg genre classifier trained in-measure on `data/corpus_fps.json`. Writes verdict JSON.
4. **render** — `core.decode_to_midi`.

## Refinement loop (`refine_loop.py`) — Generator-driven, musician-readable feedback
Single-shot newgen often fails C1 (the generator writes off-distribution textures — thin/over-syncopated).
`RefinementLoop` closes the loop automatically with any `libretto.generation` Generator:

```python
from libretto.generation.interface import ClaudeGenerator
from libretto.tasks.newgen.refine_loop import RefinementLoop
loop = RefinementLoop(ClaudeGenerator(), max_iter=3)
base = load_prompt("newgen") + "<your genre/brief context>"
best, rounds = loop.run(base, genre="jazz", context={...}, workdir="out/", label="newgen_jazz")
```
Each round: generate → `piece_fitness` (C1 non-degeneracy + length + copy_risk + genre-band fit + the
out-of-band axes from `core.genre_band_check`) → if not converged, append **grounded, non-prescriptive**
corrections (`dosage_feedback` via `core.axis_feedback`) → regenerate. The feedback states WHAT the axis
measures, WHERE the piece sits, and WHICH way to move — and lets the model choose how, e.g.
*"texture fullness (how many notes sound at once) — now ~3rd pct of real songs: raise it toward the
25–75th-percentile range (you choose how)"* rather than dictating a specific musical move or naming the raw
metric. Returns the best round (lowest structural score) + the full trajectory; leakage-free by
construction (from-scratch — no source/answer). The same `dosage_feedback`/`axis_feedback` layer backs the
gaptask loop. Honest scope: convergence is slow/noisy for full-from-scratch pieces (each round resamples
the whole piece); anchored tasks (gaptask/morph/newgen_extend) converge far more reliably.

## Autoregressive chunked mode (`chunked.py`) — recommended for from-scratch
Blind whole-piece newgen reliably fails the per-axis gate (thin texture; an unanchored generator also can't
infer conventions from context). `ChunkedNewgen` builds the piece as a chain of **validated continuations**
(gaptask-style): generate an opening chunk → validate it on the LOCAL axes (rhythm/harmony/melody/texture)
+ copy_risk → condition the next chunk on the validated seam → repeat → assemble → score with the standard
whole-piece gate. Each step is anchored, and chunk-to-chunk diversity supplies the whole-piece-only axes
(sectioning, within-song / density variation, novelty) a flat pass can't.

```python
from libretto.generation.interface import ClaudeGenerator
from libretto.tasks.newgen.chunked import ChunkedNewgen
res = ChunkedNewgen(ClaudeGenerator(), chunk_bars=16, n_chunks=5).run("electronic_dance", workdir="out/")
# res["whole_fitness"] = standard newgen gate on the assembled piece; res["chunks"] = per-chunk log
```
Per-chunk gate uses only LOCAL axes (`chunked.LOCAL_AXES`); `WHOLE_ONLY` axes are judged on the assembled
piece. Failed chunks are retried with `core.axis_feedback` corrections (`max_retry`).

**NB (encoding):** onset slots are **1-indexed** (beats on 1/5/9/13). The shared prompt (`generation/prompts/
_shared.md`) now states this — earlier from-scratch generations that used 0/4/8/12 read as fully off-beat,
which pinned `rhy_syncopation_rate` at the ceiling (the dominant historical newgen C1 failure). Anchored
tasks were immune (they copy the convention from the real context bars they're shown).

## Reproducibility
measure + render deterministic. Demo outputs: repo `compositions/newgen/` + `rendered_midi/newgen/`.
Classifier is trained deterministically on the frozen `corpus_fps.json` each run. Generation is LLM-stochastic.
