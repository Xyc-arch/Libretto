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

## Current tag: v2.0.0 — type (b) INTERFACE break (rename `musicfp`→`libretto`), core CARRIED FORWARD
v2.0.0 is a breaking interface change ONLY (the package rename); it is **NOT** a core re-validation. The
validated core is **byte-identical to v1.0.0** — encoder `midi_to_grammar.py` `6c375c4c…`, decoder
`grammar_to_midi.py` `11fc441f…`, distribution `corpus_distribution_314.json` `55b6af8e…` (sha256 all
unchanged). The frozen-core manifest was re-recorded at the SAME hashes with the new `libretto/` paths.
The validated environment below is exactly the one validated for v1.0.0.

## Tagged version
- **Distribution:** `29-axis / 314-song / 2026-06-13` (`libretto.DISTRIBUTION_VERSION`).
- **Axes:** 29 retained = 28 validated (discovery 34→30→29→28: spread filter + decorrelation on the 314
  corpus) **+ within_song_variation** (added 2026-06-13). `metrics_for` COMPUTES 35 (34 candidates + WSV);
  6 are dropped (4 spread-filter, 1 decorrelation, tex_doubling_ratio at the 314 re-filter). The retained
  set is `data/corpus_distribution_314.json` `axes_order`; all code reads `len(axes_order)` dynamically.

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
`within_song_variation` (the 29th axis) was validated to the same **statistical** depth as the 28 (same
two discovery gates: spread filter modal_share 0.404; decorrelation max |r| 0.591, full-set max stays
0.75). It was NOT exercised in the downstream held-out **experiments** — gap-task / holdout42 / newgen /
morph all ran on the 28-axis fingerprint; `corpus_fps.json` was regenerated to 29-dim afterward. Same
statistical pedigree, less experimental exposure.

## Frozen data manifest (`data/`)
| artifact | role |
|---|---|
| `corpus_distribution_314.json` | 29-axis percentile columns + per-genre bands + shapes (THE reference) |
| `corpus_fps.json` | 314 precomputed 29-dim fingerprints (retrieval + chance baseline + classifier) |
| `within_song_variation_dist.json` | the 29th axis's corpus distribution + its two gate results |
| `metric_corpus.json` | per-song raw metric cache (regenerable via `core.metric_discovery`) |
| `answer_key/grammar_truth.json` | genre labels + song identity |
| `grammar/song_0001..0315.txt` | the 314-song corpus (copy checks, retrieval, components) |
| `composing-kb/` | knowledge base (generation input, NOT measurement) |

## What is reproducible vs not
- **Reproducible (deterministic):** everything in `libretto.core` + each task's `measure`/`render`.
  Same input → identical output. Covered by `libretto/tests/test_core.py` (5 tests pass).
- **NOT reproducible:** generation (`libretto.generation` → an LLM). Canonical demo outputs are the saved
  `compositions/**` + `rendered_midi/**` in the source repo.
