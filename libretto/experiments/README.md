# experiments / attic

The packaged surface is the 4 clean pipelines (`libretto/tasks/`) on top of `libretto/core/`. The
exploratory / superseded scripts below live in the **source repo** and are intentionally NOT packaged,
so the package surface stays small. They remain in the repo for provenance.

Superseded / one-off (repo root):
- discovery & corpus build: `metric_discovery.py` (also a core tool), `build_canonical_distribution.py`,
  `expand_corpus.py`, `build_grammar_dataset.py`, `revalidate_metrics.py`, `genre_classify*.py`
- early gap-task iterations: `continuation_*`, `gaptask_setup/measure.py`, `gaptask10_*`
- abandoned variation app: `variation_setup.py`, `variation_measure.py`, `compose_abba_style.py`
- probes / smoke tests / misc: `neural_smoketest.py`, `hybrid_eval.py`, `jazz_check.py`,
  `repetition_analysis.py`, `corrupt_negatives.py`, `add_concepts.py`, `reground_kb.py`,
  `midi_to_score.py`, `render_continuation.py`, `render_gaptask.py`, `fidelity_audit.py` (audit tool)

The validated TASK scripts (gaptask21/holdout42, newgen, newgen_extend, morph) are copied into
`libretto/tasks/<task>/` as reference implementations; see each `SKILL.md`.
