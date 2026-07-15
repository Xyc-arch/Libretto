# Libretto (谱文)

**🌐 Project page & demos (listen / try the grammar): [libretto.site](https://libretto.site)**

A **descriptive** symbolic-music fingerprint environment. MIDI → a text "grammar" → a **39-axis
empirical-percentile fingerprint** against a frozen 1,523-song corpus distribution. The axes are
**discovered** (not hand-designed) and measure *typicality / structure / proximity*, **NOT quality**.

<p align="center">
  <img src="libretto/assets/workflow.png" width="920" alt="Libretto workflow"><br>
  <em>Build the environment (corpus → grammar → 39 discovered axes) · steer the agent (retrieve → compose → measure → gate, with a self-evolving loop) · six applications.</em>
</p>

The measurement layer is deterministic and reproducible. Generation is an LLM and is pluggable.

> **For agents (no prior context):** read **[`ONBOARDING.md`](ONBOARDING.md)** (repo map + the exact function to
> call for each task) and **[`AGENT.md`](AGENT.md)** (the operating prompt: grammar → axes → retrieve → compose →
> measure → loop). Provenance of the corpus is in [`DATA_PROVENANCE.md`](DATA_PROVENANCE.md).

## Install
```bash
pip install -e .            # core measurement (numpy, scipy, scikit-learn, pretty_midi, music21)
pip install -e .[generation]   # + anthropic, only for the default Generator
```
Frozen data ships inside the package (`libretto/data/`); override the location with `LIBRETTO_DATA`.

## Quickstart (deterministic — no LLM)
```python
import libretto
from libretto.core import Song, metrics_for, copy_risk, decode_to_midi, encode_from_midi

g = libretto.data_root() / "grammar" / "song_0001.txt"
m = metrics_for(Song(g), g)            # the 39 discovered axes
print(libretto.DISTRIBUTION_VERSION)    # 39-axis / 1523-song / genre-balanced / 2026-07-06
print(copy_risk(g)["copy_risk"])       # note-level overlap vs corpus
decode_to_midi(g, "out.mid")           # grammar -> MIDI
# encode_from_midi("in.mid", "adaptive", keep_drums=False, max_bars=None, anonymize=True)  # MIDI -> grammar text
```
Run the tests:
```bash
python -m pytest libretto/tests        # or: PYTHONPATH=. python -m libretto.tests.test_core
```

## Layout
```
libretto/
  core/         the 8 deterministic tools (Song, metrics_for, wsv, copy_risk, fingerprint,
                band_check, encode/decode, gaptask_channel_check) — reproducible, frozen
  data/         frozen artifacts (distribution, fps, grammar corpus, answer key, KB) — see FROZEN.md
  generation/   Generator protocol + ClaudeGenerator/EchoGenerator + per-task prompt templates
  tasks/        gaptask / newgen / morph / education (+ newgen_extend, genre_loop) — each a SKILL.md runbook
  tests/        round-trip, 39-axis shape, copy_risk self-match, determinism
```

## The six tasks
| task | what | success (structural) |
|---|---|---|
| **newgen** | compose a whole piece from scratch | length + non-degenerate + novel (copy_risk < 0.30) + genre-fit |
| **gaptask** | regenerate a held-out real region (has ground truth) | proximity to the real region + beat% (89–98% out-of-sample); gate C1/C2/C3-note + channel-check |
| **morph** | bridge song A's component into song B's | exact real ends + gradual, monotonic A→B crossfade |
| **accompaniment** | reconstruct a removed instrument voice from context | beat coverage + in-key/role fit + groove similarity + novelty vs the hidden voice |
| **anomaly** | detect and localize an injected structural anomaly | detection + false-positive rate + localization within a bar |
| **education** | single-voice piano practice drill (key · meter · concept) | single-channel + in-key + the taught challenge detected + requirements met + novelty (copy_vs_shown < 0.50) |

See each `tasks/<task>/SKILL.md` for the runbook. A **self-evolving loop** steers gaptask/newgen/education
(generate → measure → dosage feedback → regenerate, ≤3 rounds, pick-best); its per-round engine is
`core.genre_band_check` (genre-adaptive) / `core.band_profile` (global). Two auxiliary tasks ship too:
`newgen_extend` (extend/insert into a real song, no leakage) and `genre_loop` (loop reference data under
`tasks/genre_loop/refdata/`).

## Reproducibility contract
- **Deterministic & reproducible:** `libretto.core` and every task's `measure` / `render`. Same input →
  identical output. Pinned to the data version in `FROZEN.md`.
- **Not reproducible:** generation (an LLM). Plug your own model into the `Generator` protocol; the
  canonical demo outputs are the saved `compositions/**` + `rendered_midi/**` in the source repo.
- **Honest scope:** all criteria are STRUCTURAL (typicality / proximity / coherence / novelty), not quality.

See **FROZEN.md** for the tagged version, the two integrity resolutions (note-level copy gate +
the grammar↔MIDI fidelity audit), and the axis validation-scope caveat.
