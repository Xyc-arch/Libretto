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
