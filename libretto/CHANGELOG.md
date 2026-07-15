# Changelog — libretto

Versioning. A **MAJOR** bump means one of TWO things, and **each MAJOR entry MUST state which** (so a
major version never ambiguously implies re-validation):
- **(a) CORE change** — the validated core (distribution + retained axis set + encoder/decoder + metric
  definitions) changed. Requires re-running the full validation suite, a FROZEN.md note, and re-recording
  `FROZEN_CORE.sha256` with NEW hashes. Rare.
- **(b) INTERFACE break** — a breaking change to how callers use the package (e.g. a package rename, a
  removed/renamed public API) while the validated core is carried forward **byte-identical**. No
  re-validation; the frozen-core hashes are unchanged (only paths/keys in the manifest move).
- **MINOR** (e.g. v2.1.0) — new tasks / tooling / CLI / KB / generators that don't touch the core and
  don't break the interface. Frozen-core-untouched (enforced by the guard).
- **PATCH** (e.g. v2.0.1) — backward-compatible fixes outside the core, same guarantee.

The frozen core is enforced, not just documented: the pre-commit / pre-merge guard runs the core
guard-tests AND the frozen-core hash check; an unannounced core change fails the commit/merge.

## [3.0.0] — 2026-07-04 — MAJOR (a) CORE change: enriched 1612-song corpus + 39 discovered axes, re-validated
The validated core was rebuilt on a **new corpus** and re-frozen; `FROZEN_CORE.sha256` re-recorded with NEW
hashes (encoder/decoder/metric-definitions carried forward byte-identical — `midi_to_grammar` `6c375c4c…`,
`grammar_to_midi` `11fc441f…`, `metric_discovery` `5dd74b6a…`; only the distribution changed, and
`within_song_variation.py` changed by a single distribution-filename path string).

- **Corpus replaced**: the old 314-song corpus (single-author hand labels, 60 unlabeled) is superseded by
  **1612 MusicBrainz-genre-grounded songs** across 11 genres (pop_rock, funk_soul_rnb, electronic_dance,
  jazz, folk_country, classical, metal, hiphop_rap, reggae_ska, blues_gospel, latin). Encoded with the same
  frozen encoder; QC: 100% parse, note-loss <0.05%, median 8 voices; dropped single-voice + length tails.
- **Distribution is now GENRE-BALANCED**: the global CDF/percentile coordinates weight each genre equally
  (each genre resampled to K=max-genre-count) so the pop-heavy corpus no longer skews coordinates; per-genre
  bands are raw. `DISTRIBUTION_VERSION = "39-axis / 1523-song / genre-balanced / 2026-07-06"`.
- **Axes DISCOVERED from scratch** (not hand-authored): an agent proposes executable measurement functions
  and a fixed 4-principle reward retains those that spread, are non-redundant, separate genres, and agree with
  an AudioBox oracle. Over **8 rounds it proposed 134 functions and retained 39** (per-round kept:
  15,8,6,3,1,0,2,4). Set reward **0.4438 → 0.5556**; cross-validated genre macro-F1 **0.255 → 0.357**,
  balanced accuracy **0.349 → 0.436**, AudioBox agreement **0.312 → 0.435**, effective rank **9.5 → 17.7 / 39**.
  Decorrelation: max |Pearson r| **0.855** (one pair ≥ 0.85; redundancy priced into effective-rank, not
  hard-rejected); every retained axis passes the spread gate.
- **Renamed** `corpus_distribution_314.json` → `corpus_distribution.json` (all readers swept).
- **KB enriched**: `GENRE_CONCEPTS` remapped to the 11-genre taxonomy (pop_rock←core_pop_rock; +metal,
  hiphop_rap, reggae_ska, latin, blues_gospel), all from verified existing concept IDs.
- **New corpus tooling**: `libretto.corpus.build` (parallel MIDI→grammar) + `libretto.corpus.distribution`
  (parallel fingerprint + genre-balanced distribution rebuild).

## [2.3.0] — 2026-07-04 — MINOR: retrieval-ablation harness + rhythm-pattern soft coverage (frozen core untouched)
Generation-experiment tooling and a rhythm-criteria refinement; nothing touches the validated core (frozen-core
hashes unchanged; guard passes).
- **`libretto/tasks/newgen/retrieval_ablation.py`** — accumulating retrieval ON/OFF ablation (AXIS 1): builds
  matched ON (bands + KB + exemplars, seed-varied) vs OFF (bands-only) newgen prompts, scores generated grammar,
  appends to a results file, and `report()`s per-condition pass ± bootstrap SE/CI + genre-paired diff. Grows n
  over sessions (no fixed batch). CLI `python -m libretto.tasks.newgen.retrieval_ablation {prompt,add,report}`;
  results file via `$LIBRETTO_ABLATION_OUT`. Tests: `tests/test_retrieval_ablation.py`.
- **Rhythm patterns are soft coverage, not hard gates** — `data/kb_theory/rhythm.txt` reframes
  `TR-SHORT-LONG-SHORT` as a combinable *family* (0.5-1-0.5 base + variants like 0.5-1-0.25-0.25, dotted, other
  scales); `tasks/education/measure.py` detector is now family-lenient & informational (removed from the
  mandatory drill gate); `tasks/education/setup.py` prompt asks for broad rhythm-figure coverage. Rhythm variety
  is driven by the existing `rhythm_mix` check + prompt guidance, not a per-pattern gate.

## [2.2.0] — 2026-07-02 — MINOR: ABC-vs-Libretto encoding-comparison toolkit (frozen core untouched)
New subpackage `libretto.compare` — quantifies why the grammar uses an **absolute slot** for onset instead of
ABC's **relative duration**. Adds nothing to and changes nothing in the validated core (frozen-core hashes
unchanged; guard passes).
- **`cost.py`** — deterministic, model-free `encoding_cost(song)` → `onset_recovery` (Σ within-bar prefix-sum
  additions), `edit_blast` (Σ N(N−1)/2 downstream onsets re-derived per duration edit), `vertical_align`
  (additions to align voices = read "what sounds together"); Libretto's absolute slot = **0** for all three.
  `corpus_cost()` aggregates over the corpus.
- **`abc.py`** — emit the SAME music as ABC (relative) and Libretto (absolute slots) from one event list, with
  `roundtrip_ok()` verifying both re-parse to an identical (voice, onset, pitch) set (via the frozen codec).
- **`benchmark.py`** — reproducible **tool-free** ABC-vs-Libretto reading benchmark: stimuli + objective
  questions + computed ground truth (tasks T1–T7 + `build_hallucination()`), a scorer that compares by musical
  identity, an `impossible()` out-of-meter **hallucination** metric (0 for a Libretto slot by construction), and
  a self-validating `oracle()`. The LLM run is external. CLI: `python -m libretto.compare {cost,benchmark}`.
- Also fixes packaging: `libretto.validation` and `libretto.compare` are now listed in `pyproject` packages
  (validation was previously omitted from the wheel). Tests: `tests/test_compare.py`.
- Full write-ups, real Nottingham-tune data, and figures remain in `paper_data/grammar_compare/`.

## [2.1.0] — 2026-06-25 — MINOR: external axis-validation toolkit (frozen core untouched)
New subpackage `libretto.validation` — causal, external validation of the structural axes via dose-response
against an independent human-preference proxy (Meta AudioBox-Aesthetics). Adds nothing to and changes nothing
in the validated core (frozen-core hashes unchanged; guard passes).
- **`levers.py`** — extensible registry of per-axis perturbations (`@lever(axis, push)` / `register_lever`);
  ships the 25 leverable canonical axes. **`UNCOVERED`** documents the 4 emergent axes (chord-set / SSM
  statistics) that have no isolated handle, with reasons.
- **`judge.py`** — `Judge` protocol + default `AudioBoxJudge` (pluggable: bring your own preference model).
- **`validate.py`** — dose-response engine → per-axis `within_rho`, `delta` (ΔCE extent), `sign_p` (sign test),
  `entangled`, `validated`; `summarize()` is pure/unit-tested. CLI: `python -m libretto.validation`.
- Lets contributors validate **new** axes they design with the same machinery. Tests: `tests/test_validation.py`.
- `paper_data/axis_perturb.py` and `paper_data/_audiobox_score.py` are now thin shims re-exporting the package;
  `paper_data/axis_quality_validation.py` is a thin driver over `libretto.validation.validate`.

## [2.0.0] — 2026-06-14 — MAJOR: type (b) INTERFACE break (package rename) — NOT a core re-validation
**This MAJOR is an INTERFACE break, not a core change.** The validated core is carried forward
**byte-identical** to v1.0.0 — no re-validation was performed and none was needed.

- **Why MAJOR:** the package was **renamed `musicfp` → `libretto`** (import path + env var
  `MUSICFP_DATA`→`LIBRETTO_DATA`). Existing `import musicfp` code breaks → a breaking interface change,
  which is a MAJOR under standard semver.
- **Core is byte-identical (proof):** encoder `midi_to_grammar.py` sha256 `6c375c4c…`, decoder
  `grammar_to_midi.py` `11fc441f…`, and distribution `corpus_distribution_314.json` `55b6af8e…` are
  **unchanged from v1.0.0**. Only `metric_discovery.py` / `within_song_variation.py` differ, solely in
  the env-var string. The frozen-core manifest was re-recorded **at the same hashes, new paths** — the
  re-record reflects the rename, not new substance. The 29-axis / 314-song / 2026-06-13 distribution and
  all metric/encoder logic are exactly v1.0.0.
- **Also in this release (tooling, non-breaking):** promoted the self-evolving loop onto the package surface:
  - `core.genre_band_check` — the per-round engine, **general & genre-ADAPTIVE** (any of the 9 genres,
    or global). Replaces the old genre-fixed `jazz_check`: split axes judged vs the target genre's band
    (target p50, out-of-band either direction); a pinned genre band widens to that genre's data-driven
    [p5,p95] (no hardcoded per-genre exception). `genre=None` = pure global-band check.
  - Exported `band_profile` / `band_status` (global-band drift verdict) from `core`.
  - New `tasks/genre_loop/` — SKILL.md runbook (setup → per-round check → dosage adjust → converge →
    gate) + shipped canonical round-by-round reference data: `refdata/jazzloop/` (5 rounds + results)
    and `refdata/evolve_loop_soul/` (the original soul-groove loop where the mid-band dosage lesson began).
  - Added `tests/test_genre_loop.py` (genre-adaptivity, data-driven widening, global mode).

## [1.0.0] — 2026-06-14 — validated baseline
The validated, integrity-resolved, fidelity-audited environment.
- 29-axis fingerprint (28 validated + within_song_variation) vs the frozen 314-song distribution.
- Deterministic core (Song, metrics_for, wsv, copy_risk, fingerprint, band_check, encode/decode,
  gaptask_channel_check) shipped with frozen package data.
- Integrity resolved: copy gate unified at NOTE level; gap-task answer-overlap verified 100%
  context-explained (CLEAN, not leakage) via the channel-check.
- Grammar↔MIDI fidelity audit: faithful on claimed dimensions (pitch exact, onset/duration within grid,
  voice 1:1; genuine note-loss 0.019%); admitted losses quantified. See log/FIDELITY_AUDIT.md.
- Four tasks (gaptask / newgen / newgen_extend / morph) as SKILL.md runbooks + reference scripts.
- Generator protocol + per-task prompts (the one non-deterministic seam).
- Guard-tests: 29-axis shape, exact round-trip, determinism, copy_risk self-match — all pass.
