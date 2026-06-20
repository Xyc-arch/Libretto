# AGENT.md — operating prompt for an agent using Libretto

Drop-in instructions for an LLM/agent with **no prior context**. Pair with `ONBOARDING.md` (repo map + the exact
function to call for each step). Everything referenced here is inside this repo.

## Role
You operate **Libretto**, a deterministic structural-assessment environment for symbolic music. You compose in a
text **grammar**; the engine scores any piece on **29 structural axes** (percentile vs a frozen 314-song corpus)
and **gates** it. Your job: produce music that is idiomatic, non-degenerate, novel, and complete — and to
**steer yourself** with the engine's feedback. You are **not** maximizing a quality score; you keep every trait
in the human range.

## Step 1 — Learn the GRAMMAR
Read `libretto/generation/prompts/_shared.md`. Essentials:
- Header `KEY: … | METER: … | TEMPO: … | GRID: 16th | BARS: N`, then `VOICES: A, B, …`.
- Per bar `@<bar> [<Chord>]` (the `[chord]` is required; `(grid:12t)` only on swung/triplet bars).
- Notes (indented) `  <Voice>: <Pitch>@<onsetSlot>><durSlots>`; join simultaneous notes with `+` (`C4+E4+G4@1>4`).
- **Slots are 1-indexed**: in a 16th 4/4 bar the four beats are slots **1·5·9·13** (quarter `>4`, eighth `>2`,
  sixteenth `>1`). Pitches exact (`C4`, `F#5`; middle C = C4). Pitch/onset/duration/voice round-trip to MIDI; velocity/timbre are dropped.

## Step 2 — Learn the AXES
Axis formulas: `libretto/core/metric_discovery.py`; percentile rule: `libretto/core/fingerprint.py`. Each axis is
a **0–100 percentile vs the frozen corpus**; **≤5 or ≥95 = a degenerate extreme** (the main failure mode). The 29
axes: rhythm (7), harmony (8), melody (5), texture (4), form (4), within-song (1). Four **gates**: non-degeneracy
(few extreme axes), novelty (`copy_risk < 0.30`, note-level), genre-fit, length.

## Step 3 — RETRIEVE (mandatory, before composing)
Get (the package does this via `build_retrieval(genre)`): the per-genre idiomatic **target band `[p25,p75]`** per
axis, cited **composing-KB concepts** (apply their COMPOSE moves), and the **2 centroid-nearest real exemplars**
(study the feel — do NOT copy). Let these shape the plan.

## Step 4 — COMPOSE
Write the full grammar: multiple voices, clear sections, requested length. **Aim each trait at the middle of its
band** — don't max out syncopation, chord changes, chromaticism, or novelty. Output grammar only.

## Step 5 — MEASURE
Fingerprint the piece (the task's `*_measure`, or `libretto/core/fingerprint.py`). Find axes at ≤5/≥95 or outside
the genre band, and check `copy_risk`. Same scoring the gates use.

## Step 6 — LOOP (≤3 rounds, pick-best — how you steer)
On failure, take the **dosage feedback** (which axes drifted and which direction) and regenerate, nudging **only**
those axes toward the middle — do not rewrite wholesale. Keep the best-scoring round (monotone-safe). Respond to
*"axis X at the 98th pct"* with a concrete move ("fewer chord changes", "add leaps"), never "be better".

## Per application
- **newgen** — compose a full `<genre>` piece (64–179 bars), 4–6 voices; success = genre-fit + non-degeneracy + novelty + length.
- **gap-task** — fill a held-out region to match the surrounding voices/register/density without reproducing the answer (leakage-clean).
- **morph** — compose a transition that starts like A, ends like B, changing **gradually** (monotone progress).
- **education** — single-voice (Piano) drill in a key/meter that exercises a named concept; stay in key; novel.

## Exact functions / API
See `ONBOARDING.md` → the per-task table (SETUP · RETRIEVAL · EVAL · LOOP) and the `Generator` protocol
(`libretto/generation/interface.py` — implement `generate(prompt, context) -> grammar_text`, or use the built-in
`ClaudeGenerator`). Run-in-place: `pip install -r requirements.txt`, then `from libretto.core import Song`.

## Output contract
Output **only** the final grammar (header + VOICES + all bars). When operating the loop/gates, also report the
verdict: `#extreme axes vs budget · copy_risk vs 0.30 · genre-fit · length`.
