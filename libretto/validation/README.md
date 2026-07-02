# libretto.validation — external, causal validation of structural axes

The 29-axis fingerprint is **descriptive** — it locates a song in statistical space, with no notion of
"good". This module asks a different, *causal* question with an **independent** judge:

> If an axis captures real, quality-relevant structure, then pushing a song toward that axis's extreme
> should make it sound **worse** to a model that knows nothing about our axes.

We test it as a **dose-response**: for each seed song and axis, push the axis toward its extreme over graded
doses `[0, 0.33, 0.66, 1.0]` (holding instrumentation fixed), render identically, and score with
[Meta AudioBox-Aesthetics](https://github.com/facebookresearch/audiobox-aesthetics) content-enjoyment (CE) —
a learned **proxy for human audio preference**. A negative within-song correlation of CE with dose validates
the axis.

## What you get per axis

| field | meaning |
|---|---|
| `within_rho` | within-song Spearman(dose, CE), averaged across songs — the headline (each song is its own control) |
| `delta` | mean CE(strongest push) − CE(unchanged) — effect **extent** in the judge's units |
| `sign_p` | one-sided sign test across songs — did they agree on direction more than chance? |
| `entangled` | mean # of *other* axes that co-moved (re-fingerprinted) — keeps single-axis attribution honest |
| `validated` | `within_rho ≤ −0.5`, negative in **every** contributing song, and ≥ 3 contributing songs |

## Use it

```python
from libretto.validation import validate

res = validate()                       # 8 genre-spread songs × all registered levers (needs setup below)
print(res.n_validated, "validated")
for a in res.axes:
    print(f"{a.axis:28} ρ={a.within_rho:+.2f} ΔCE={a.delta:+.2f} p={a.sign_p:.3f} {'✓' if a.validated else ''}")
res.write_csv("axis_quality_dose.csv")
print(res.coverage())                  # {'canonical': 29, 'levered': 25, 'uncovered': {...}}
```

CLI:

```
python -m libretto.validation                       # full run (AudioBox)
python -m libretto.validation --coverage            # just the 25/29 coverage + reasons, no run
python -m libretto.validation --axes mel_voice_range,tex_voice_count --out out.csv
python -m libretto.validation --full                # score the entire render (slow)
```

### Setup (one time)

```bash
# isolated AudioBox env (its torch can't share the base env)
python3.11 -m venv .venv_audiobox
.venv_audiobox/bin/pip install audiobox_aesthetics==0.0.4    # pulls torch 2.2.2; first run downloads the checkpoint
# system: fluidsynth (brew install fluid-synth) + a soundfont (MuseScore "MS Basic.sf3" auto-detected,
#         or set $LIBRETTO_SOUNDFONT). Point at the venv with $LIBRETTO_AUDIOBOX_PY if it isn't ./.venv_audiobox.
```

## Adding a new axis

To validate a **new** axis you design, give it a *lever* — a function that pushes it toward an extreme by
editing the grammar text. Register with the decorator (the axis name must be a key produced by
`libretto.core.metric_discovery.metrics_for`, i.e. measurable by the fingerprint):

```python
from libretto.validation import lever, validate

@lever("rhy_my_new_axis", push="high")
def push_my_axis(grammar_text, dose):
    # ... edit grammar_text toward the axis's HIGH extreme, scaled by dose in [0,1] (0 = unchanged) ...
    return grammar_text

res = validate(axes=["rhy_my_new_axis"], songs=["song_0047", "song_0009"])
```

The validator **re-fingerprints every perturbed output**, so it will tell you (a) whether your lever actually
moved the target axis toward its extreme, and (b) how many *other* axes it dragged along (`entangled`). A good
lever moves its target monotonically and little else. Use a custom judge by passing any object with a
`primary` attribute and a `score(wav_paths) -> [{metric: value}, ...]` method (see `judge.py`).

## Why only 25 of the 29 axes have a lever

Four canonical axes are **emergent statistics over the whole chord-set / self-similarity structure**, with no
isolated grammatical handle — any edit that moves them also strongly moves several correlated axes, so a clean
single-axis dose-response (and thus honest attribution) is impossible:

- `har_chord_change_rate` — harmonic-rhythm turnover; needs an all-voice rewrite (moves pc-entropy, simultaneity, root motion).
- `har_vocab_density` — size of the distinct chord vocabulary; redesigning it drags distinct-pc, chromaticism, pc-entropy.
- `har_fourth_motion_rate` — fraction of fourth/fifth root motions; needs a coherent bass-root rewrite (entangles root-motion-entropy).
- `form_section_per100bars` — section count from the self-similarity matrix; you can't add a section boundary locally without restructuring repetition.

This is a limitation of the **perturbation method**, not of the axes — they remain valid descriptive
coordinates; they just can't be *causally* externalised this way. They are listed with reasons in
`validation.UNCOVERED` and surfaced by `ValidationResult.coverage()` / `--coverage`.

> **Honesty note.** AudioBox CE is a learned proxy for human preference and is confounded by the fixed
> soundfont render. These results are valid for **relative** comparison within one identical render pipeline,
> never as an absolute quality gate.
