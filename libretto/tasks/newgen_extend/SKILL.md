# SKILL: newgen_extend — extend/insert into an existing song (no leakage)

Invent a NEW region attached to a real song (continuation / prefix / insertion). No held-out answer,
so copy_risk guards against parroting the source rather than reading an answer.

## Criteria (verdict)
- **COHERES** — `D(region,source) ≤ 22` over length-stable STYLE axes (28 − 5 length-artifact).
- **non-degenerate** — genre-aware C1 with length-axis + source-shared-extreme exemptions.
- **genuinely-new** — `copy_risk` < 0.30 vs source AND corpus.
- **boundary** — voice-Jaccard ≥ 0.5 AND seam pc-set Jaccard ≥ 0.10 at the nearest sounding bar.
- *Insertion caveat:* a bridge may contrast (D>22 ok) if non-degenerate + new + boundary-connected AND
  D < its chance baseline.

## 4 verbs
1. **setup** — `newgen_extend_setup.py`: choose source + attach point, retrieve neighbors, build context.
2. **generate** — feed `prompts/newgen_extend.md` + context to a `Generator`. Save `<id>_gen.txt`.
3. **measure** — `newgen_extend_measure.py`: style-axis coherence, C1 (with exemptions), `copy_risk`
   vs source+corpus, boundary continuity (uses `core.pattern_catalog` seam pcs). Writes verdict JSON.
4. **render** — `core.decode_to_midi` (full + new-region).

## Reproducibility
measure + render deterministic. Demo outputs: repo `compositions/` (newgen_extend cases) +
`rendered_midi/newgen/`. Generation is LLM-stochastic.
