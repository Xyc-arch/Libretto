# SKILL: morph — bridge one song's component into another's (song -> song)

Generate a transition whose fingerprint travels A -> B: start = an exact real component of A, end = an
exact real component of B, middle = a gradual thematic crossfade.

## Criteria (component-morph)
- **exact real-component ends** (the two anchor bars are real, unaltered).
- **START** close to A (progress ≤ 0.30, copy-A high) · **END** close to B.
- **GRADUAL** — per-bar progress A->B monotonic (±0.10 noise) AND max step ≤ 0.40.
- **CROSSFADE** — copy-A falls and copy-B rises across the transition.
- pure-generated middle copy rate reported (mostly original; seams relaxed to enable the glide).

## 4 verbs
1. **setup** — `morph_setup.py`: pick song pair, extract first-8-sounding-bar components, build per-axis
   rampable A->B targets and the transition brief.
2. **generate** — feed `prompts/morph.md` + context to a `Generator`. Save the transition grammar.
3. **measure** — `morph_measure.py` (rampable trajectory) + `morph_component_measure.py`
   (START/END/GRADUAL/CROSSFADE, copy via `core.copy_risk` slide). Writes verdict JSON.
4. **render** — `core.decode_to_midi`: songA / gen_only / gen_with_real_neighbors / songB stems.

## Reproducibility
measure + render deterministic. Demo outputs: repo `rendered_midi/morph/<genreA>_to_<genreB>__<sidA>_<sidB>/`
(8 pairs). Generation is LLM-stochastic.
