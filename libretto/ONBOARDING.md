# Libretto — onboarding

Libretto is a **descriptive, deterministic structural-assessment environment for symbolic music**. It encodes
MIDI as a text **grammar**, scores any piece on a **39-axis empirical-percentile fingerprint** against a frozen,
genre-balanced 1,523-song reference distribution, and **steers an LLM** to compose music that passes deterministic gates. The measurement layer
is fully reproducible; the LLM is a pluggable seam.

This package (`libretto/`) is self-contained — corpus, distribution, prompts, knowledge bases, tasks, and tests
all ship inside it. Nothing outside this directory is required to run or reproduce it.

## Get it running (no install needed)
Python ≥ 3.11. The code imports itself as `libretto.*`, so keep this folder named `libretto/` and run from the
directory **containing** it.
```bash
pip install -r libretto/requirements.txt      # numpy, scipy, scikit-learn, pretty_midi, music21
pip install "anthropic>=0.40"                  # optional — only for the built-in ClaudeGenerator (needs ANTHROPIC_API_KEY)
python3 -c "from libretto.core import Song; print('ok')"
```
Edit any module and it takes effect immediately (run-in-place). `pip install -e .` also works if pyproject.toml
is at the repo root (see "Packaging note" at the end).

## Repository structure
```
libretto/
├── __init__.py            # data_root(), DISTRIBUTION_VERSION ("39-axis / 1523-song / genre-balanced / 2026-07-06"), __version__
├── VERSION  FROZEN.md  FROZEN_CORE.sha256  CHANGELOG.md  README.md  requirements.txt  pyproject.toml
├── core/                  # deterministic measurement layer (frozen) — NO LLM
│   ├── understanding_probe.py   # Song: parse grammar text → events
│   ├── axes_v3.py               # axes_v3.metrics_for(song) → 39 v3 axes (REGISTRY; the live fingerprint axes)
│   ├── metric_discovery.py      # (legacy v2 metric bank; superseded by axes_v3)
│   ├── within_song_variation.py # wsv() — (legacy v2 axis; folded into axes_v3)
│   ├── fingerprint.py           # profile(path) → 39-axis percentiles vs the frozen corpus
│   ├── midi_to_grammar.py       # encode (MIDI → grammar)        decode counterpart below
│   ├── grammar_to_midi.py       # decode (grammar → MIDI)
│   ├── copy_risk.py             # note-level novelty / copy detection
│   ├── band_check.py · genre_band_check.py · axis_feedback.py   # loop feedback: out-of-band axes → musical nudges
│   └── gaptask_channel_check.py · pattern_catalog.py
├── generation/
│   ├── interface.py       # Generator protocol + ClaudeGenerator + EchoGenerator
│   └── prompts/           # _shared.md (grammar spec) + gaptask/newgen/newgen_extend/morph .md
├── tasks/                 # one dir each; every task has a SKILL.md runbook
│   ├── gaptask/  newgen/  newgen_extend/  morph/  education/  genre_loop/
│   │                      # setup (build prompt+retrieval) · *_measure (gate) · refine_loop (≤3-round loop)
├── validation/           # external axis-validation (dose-response vs AudioBox) — no LLM; see validation/README.md
├── compare/              # Libretto-vs-ABC encoding cost + tool-free reading benchmark — no LLM; see compare/README.md
├── data/                  # frozen artifacts
│   ├── corpus_distribution.json       # THE reference (39 axes × 1,523 genre-balanced songs + genre bands)
│   ├── corpus_fps.json · metric_corpus.json · within_song_variation_dist.json · newgen_calibration.json
│   ├── grammar/song_*.txt             # the 1,612-song corpus (text grammar)
│   ├── answer_key/grammar_truth.json  # per-song artist/title/genre (curated from Lakh clean_midi)
│   ├── composing-kb/                  # 34 corpus-attested idiom concepts (newgen retrieval)
│   └── kb_theory/                     # 193 music-theory concepts, each with a GRAMMAR example (education retrieval)
├── tests/                 # pytest (round-trip, 39-axis shape, determinism, copy self-match)
├── tools/check_frozen_core.py         # sha256 integrity of the frozen core
└── experiments/           # scripts/notes from the validation runs
```

## What you can do — and where each piece lives

**Shared core (any piece, no LLM)** — `libretto.core`:
- `fingerprint.profile(path)` → per-axis percentiles (0–100; ≤5 or ≥95 = degenerate extreme).
- `copy_risk.copy_risk(path)` → note-level novelty (from-scratch gate `< 0.30`).
- `grammar_to_midi.decode` (= `decode_to_midi`) / `midi_to_grammar.encode` (= `encode_from_midi`) — render / ingest.
- `band_check`, `genre_band_check`, `axis_feedback` — turn out-of-band axes into musical nudges (loop feedback).

**Analysis & extension subpackages (no LLM):**
- `libretto.validation` — causally validate any structural axis via dose-response against an independent
  human-preference proxy (AudioBox-Aesthetics). Register a lever for a new axis and the same machinery reports
  `within_rho` / ΔCE / sign-test / entanglement. CLI: `python -m libretto.validation`. See `validation/README.md`.
- `libretto.compare` — why onset is an **absolute slot**, not an ABC-style relative duration: `encoding_cost(song)`
  (model-free onset-recovery / edit-blast / vertical-alignment cost; Libretto = 0) plus a reproducible **tool-free
  ABC-vs-Libretto reading benchmark** (stimuli + ground truth + scorer + out-of-meter hallucination metric). CLI:
  `python -m libretto.compare {cost,benchmark}`. See `compare/README.md`.

**Every task = 4 verbs: SETUP (build prompt + retrieval) → GENERATE (your model) → EVAL (measure/gate) → LOOP
(optional, ≤3 rounds, pick-best).** Exactly where each is implemented:

| task | SETUP (prompt) | RETRIEVAL | EVAL / gate | LOOP |
|---|---|---|---|---|
| **newgen** | `newgen/newgen_setup.py` → `build_genre_prompt(genre)` / `build_brief_prompt(brief)` | `newgen/retrieval.py` → `build_retrieval(genre)` (bands+KB+exemplars; called by setup) · thresholds `newgen/calibrate.py` → `c1_budget/fit_threshold/copy_threshold(genre)` | per-round `newgen/refine_loop.py` → `piece_fitness(path,*,genre)` · full `newgen/newgen_measure.py` → `measure(piece,target)` | `newgen/refine_loop.py` → `RefinementLoop(gen,max_iter=3).run(prompt,*,genre,workdir,label)` + `dosage_feedback(fit)` |
| **gaptask** | `gaptask/holdout42_setup.py` (writes ctx + held-out region; neighbors via `holdout_select.py`) | context = the surrounding bars (neighbors auto-selected; no KB) | loop-time `gaptask/refine_loop.py` → `region_fitness(region,ctx,*,genre,target_bars,neighbor_ids)` (**never sees the answer**) · final `final_grade(region,real,ctx,*,genre,neighbor_ids)` | `gaptask/refine_loop.py` → `RefinementLoop(gen).run(case,workdir,brief_builder)` + `dosage_feedback(fit)` |
| **morph** | `morph/morph_setup.py` → `main(A,B,S=6,seg_bars=9)` | references = the real A & B components (no KB) | `morph/morph_measure.py` → `main(path,A,B,S)` · per-segment `morph_component_measure.py` | *single-pass* (no refine_loop) |
| **education** | `education/setup.py` → `build_prompt(spec)` · concept pick `education/curriculum.py` → `autoscale(...)` | `education/retrieval.py` → `build_context(concept_ids, with_exemplar=True)` (kb_theory) | `education/measure.py` → `measure(path,case)` · `education/grade.py` → `difficulty_grade/detect_training/analyze` | `education/refine_loop.py` → `RefinementLoop(gen).run(spec,workdir,label)` + `feedback(report)` |
| **newgen_extend** | `newgen_extend/newgen_extend_setup.py` → `main(sid,typ)` | source-song context | `newgen_extend/newgen_extend_measure.py` → `main(sid,typ,rpath)` | *single-pass* (no refine_loop) |
| **genre_loop** | reference/demo only (just `__init__.py`) | — | — | — |

**The model seam** — `libretto/generation/interface.py`: implement the `Generator` protocol
(`generate(prompt, context) -> grammar_text`); built-ins `ClaudeGenerator()` (needs `ANTHROPIC_API_KEY`) and
`EchoGenerator()` (tests). `load_prompt(task)` loads the task's prompt template from `generation/prompts/`.
The grammar spec the model must follow is `generation/prompts/_shared.md`; per-axis formulas are in
`core/metric_discovery.py`.

### End-to-end example (newgen)
```python
from libretto.tasks.newgen.newgen_setup import build_genre_prompt
from libretto.tasks.newgen.refine_loop import RefinementLoop, piece_fitness, dosage_feedback
from libretto.generation.interface import ClaudeGenerator   # or your own Generator
from libretto.core import decode_to_midi

prompt, case = build_genre_prompt("jazz")                    # SETUP (+ retrieval baked in)
loop = RefinementLoop(ClaudeGenerator(), max_iter=3)         # GENERATE + EVAL + LOOP
best, rounds = loop.run(prompt, genre="jazz", workdir="out/", label="jazz")
#   each round: generate → piece_fitness(path, genre="jazz") → if failing, dosage_feedback(fit) → regenerate
#   best = {bars, c1_pass, copy_pass, genre_fit, converged, score, ...}   (pick-best, monotone-safe)
decode_to_midi(best["path"], "out/jazz.mid")                 # render the winner
```
Swap `build_genre_prompt`→the task's setup and `RefinementLoop`→the task's loop (per the table) for the others.

## Reproduce exactly
The **measurement layer is deterministic** — same input → identical output — so any agent reproduces the same
fingerprints, gates, and renders bit-for-bit. **Generation (the LLM) is not** reproducible.
```bash
python3 libretto/tools/check_frozen_core.py     # sha256 of the 5 frozen-core files == pinned v2.0.0 manifest
python3 -m pytest libretto/tests/               # round-trip · 39-axis shape · determinism · copy self-match
```
The **frozen core** = `data/corpus_distribution.json`, `core/midi_to_grammar.py`, `core/grammar_to_midi.py`,
`core/metric_discovery.py`, `core/within_song_variation.py`. Changing any of these moves *all* fingerprints and
`check_frozen_core.py` will flag it — treat that as a deliberate re-validation + version bump, not a routine edit.
Everything else (tasks, prompts, generators, KB, tools) is free to modify. `FROZEN.md` records the contract.

## Packaging note (before you ship)
`pyproject.toml` declares `packages = ["libretto", "libretto.core", "libretto.generation", "libretto.tasks",
"libretto.validation", "libretto.compare"]`, i.e. it expects `libretto/` to be a package directory at the **repo
root**. So the GitHub repo should expose this folder as `libretto/` with `pyproject.toml` at the root (one level
up from the package). `package-data` ships the frozen data, both KBs (`data/composing-kb/**`, `data/kb_theory/**`),
`answer_key`, grammar corpus, prompts, and the per-subpackage READMEs. One thing to confirm for a clean
`pip install`: move `pyproject.toml`/`README`/`VERSION` to the repo root if you want install-from-clone. Shipping
the **source tree** as-is (run-in-place) needs no fix.
