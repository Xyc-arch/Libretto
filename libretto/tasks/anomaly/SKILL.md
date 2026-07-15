# SKILL: anomaly — "spot the deliberate error" (music anomaly detection)

Inject ONE subtle, music-tradition-violating anomaly into a coherent piece (a COPY — the corpus is never
touched), then test whether a TOOL-FREE reasoner can find it: is there an anomaly? which bar? what kind?

## Pipeline (all pkg-native, reproducible)
1. **inject** (`inject.py`) — 6 PURE injectors, each returns a modified COPY + ground truth (bar, kind), one
   line changed, seeded target bar. Kinds: `out_of_key`, `wrong_bass`, `dissonance`, `meter_glitch`,
   `voice_crossing`, `parallel_fifths` (voice-leading kinds exclude drum voices).
2. **build_cases** (`build_cases.py`) — reads source READ-ONLY, writes clean + anomalous copies to a SEPARATE
   dir; balanced n clean + n anomalous. Sources:
   - `--source corpus` (real songs) — but real music idiomatically contains every anomaly, so a real-song
     "clean" control is CONFOUNDED (see finding). `--excerpt-bars N` for short windows.
   - `--source clean` — GENERATED theory-clean SATB chorales (`clean_source.py`), verified anomaly-free — the
     valid clean control.
3. **clean_source** (`clean_source.py`) — diatonic 4-voice chorales clean by construction (bass=root, triad
   tones only, ordered voices, whole notes), candidate-enumeration voicer + parallel-free voice-leading,
   rejection-sampled and VERIFIED.
4. **verify** (`verify.py`) — `is_clean(text)` runs all 6 anomaly checks (verifies clean_source output; also a
   transparent rule-detector baseline).
5. **probe** (`probe.py`) — `claude -p` with NO tools (reasons about harmony/key/meter, cannot compute) says
   {anomaly, bar, kind}. Graded: detection / false-positive / localization ±1 / kind — LLM vs the heuristic.

    python -m libretto.tasks.anomaly.build_cases --n 20 --seed 1 --source clean
    python -m libretto.tasks.anomaly.probe --cases paper_data/anomaly_v3_clean/cases --model opus

## Key finding (see paper_data/EXP_RESULTS_anomaly.md)
On a GENUINELY theory-clean control, Opus is a near-perfect detector: **1.00 detection, 0.00 false-positive,
1.00 localization** (and beats a rule detector, 1.00 vs 0.60, by catching voice-leading/bass anomalies rules
miss). The high FP on real songs (0.30 full / 0.67 excerpt) was a CONFOUNDED-CONTROL artifact — real music
contains the very features we inject, so a clean control MUST be synthetic. Remaining weakness: kind labelling
(0.50) — the model finds WHERE reliably but sometimes mislabels WHAT.

## Contract
Injectors are PURE (never mutate the corpus). Cases go to a separate dir. Tests: `libretto/tests/test_anomaly.py`.
