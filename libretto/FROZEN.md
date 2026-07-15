# FROZEN — libretto (validated environment tag)

This package pins ONE validated version of the environment. Numbers in any result file are tied to it.

## Versioning rule (MAJOR is two-sided — always say which)
A **MAJOR** bump means ONE of two things, and the CHANGELOG entry MUST state which, so a major version
never ambiguously implies re-validation:
- **(a) CORE change** — the validated core (distribution + retained axis set + encoder/decoder + metric
  definitions) changed. Requires re-running the full validation suite and re-recording
  `FROZEN_CORE.sha256` with NEW hashes.
- **(b) INTERFACE break** — a breaking change to how callers use the package (rename, removed/renamed
  public API) with the validated core carried forward **byte-identical** (frozen-core hashes unchanged;
  only manifest paths move). No re-validation.

MINOR = non-breaking new tooling that doesn't touch the core. PATCH = backward-compatible fixes.

## Current tag: v3.0.0 — type (a) CORE change (enriched 1612-song corpus + 39 discovered axes, re-validated)
v3.0.0 rebuilds the validated core on a **new corpus** and re-records `FROZEN_CORE.sha256` with NEW hashes.
The old 314-song corpus (single-author hand labels, 60 unlabeled) is **replaced** by 1612
MusicBrainz-genre-grounded songs across 11 genres. The corpus is the **enriched 1612-song grammar**
(carries `[prog=N]` GM instruments, `[drums]` percussion voices, `^V` coarse velocity); the frozen core
is (`corpus_distribution.json`, `midi_to_grammar.py`, `grammar_to_midi.py`, `axes_v3.py`) — see
`FROZEN_CORE.sha256`. The global distribution is **genre-balanced** (each genre weighted equally in the
CDF/percentiles; per-genre bands raw, for all axes). The decoder now round-trips **losslessly** (same-pitch
overlaps split across lanes; core guard + 120/120 corpus sweep clean).

## Tagged version
- **Distribution:** `39-axis / 1523-song / genre-balanced / 2026-07-06` (`libretto.DISTRIBUTION_VERSION`).
- **Axes:** the coordinate system is **39 axes DISCOVERED from scratch** by the `axis_evolve` self-loop
  (spread + decorrelation gates, balanced-CV genre separability as the objective, audiobox CE/PC agreement
  as a tie-breaker) — replacing the hand-authored 28 metric_discovery axes + `within_song_variation`
  (preserved in git history). Definitions live in `libretto/core/axes_v3.py`; the retained set is
  `data/corpus_distribution.json` `axes_order` and all code reads `len(axes_order)` dynamically. Run
  provenance: `axis_evolve/state/TRACE.md`.

## Integrity resolutions baked into this freeze
1. **Copy gate — unified at NOTE level (2026-06-14).** All tasks gate the note-level `copy_risk`.
   gap-task's answer-overlap was checked with `core.gaptask_channel_check`: **100% context-explained
   reprise on holdout-42 (99% on gaptask-21) — CLEAN, no leakage, no exclusions.** Bar-level C3 retained
   in the repo `validity_gate.py` for the record but superseded.
2. **Grammar↔MIDI fidelity audit (2026-06-14, `log/FIDELITY_AUDIT.md`, 18 files / 9 genres).** The grammar
   is FAITHFUL on its claimed dimensions; losses confined to the admitted ones (working as designed):
   - pitch exact (distinct pitch set preserved 100%; genuine note-loss **11 of 57,885 = 0.019%**),
     onset within grid (median 0 ms, mean 3.1 ms), duration within grid, voice 1:1.
   - admitted losses, quantified: velocity flattened (source 5–106 distinct values); micro-timing
     quantized (tail ~one slot); **drums dropped (0–68% of source notes, mean 21%)**; instrument
     identity reassigned (keyword→GM).

## Validation-scope caveat (state honestly)
All **39 axes** are validated STATISTICALLY (spread gate + decorrelation, max |Pearson r| 0.855 with one pair
≥ 0.85, effective rank 17.7/39) and by held-out genre separability (macro-F1 0.371 → 0.437 on 260 songs never
in discovery, chance 0.091). CAUSAL steerability, however, is only tested on the subset of axes that have a
deterministic grammar-surgery lever: **14 axes are intervention-tested**, of which **7 are CE-responsive**
(mean within-song ρ(dose, AudioBox-CE) ≤ −0.5); the intervention is monotone in 94% of 200 axis·song·direction
cases. The remaining axes are descriptive coordinates with the same statistical pedigree but no verified causal
lever. Because AudioBox contributes to discovery, the CE result demonstrates transfer to fresh songs under the
same evaluator, not independent human validation.

## Frozen data manifest (`data/`)
| artifact | role |
|---|---|
| `corpus_distribution.json` | 39-axis genre-balanced percentile columns + per-genre bands + shapes (THE reference) |
| `corpus_fps.json` | 1525 precomputed 39-dim fingerprints (retrieval + chance baseline + classifier) |
| `within_song_variation_dist.json` | a within-song-variation axis's corpus distribution + its two gate results |
| `metric_corpus.json` | per-song raw metric cache (regenerable via `core.metric_discovery`) |
| `answer_key/grammar_truth.json` | genre labels + song identity |
| `grammar/song_*.txt` | the 1612-song genre-grounded corpus (copy checks, retrieval, components) |
| `composing-kb/` | knowledge base (generation input, NOT measurement) |

## What is reproducible vs not
- **Reproducible (deterministic):** everything in `libretto.core` + each task's `measure`/`render`.
  Same input → identical output. Covered by `libretto/tests/test_core.py` (5 tests pass).
- **NOT reproducible:** generation (`libretto.generation` → an LLM). Canonical demo outputs are the saved
  `compositions/**` + `rendered_midi/**` in the source repo.
