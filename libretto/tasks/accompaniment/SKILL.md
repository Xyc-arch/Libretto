# SKILL: accompaniment — reconstruct a removed instrument track

Mask one whole instrument VOICE (bass / drums / harmony), keep the rest as context, and have an agent compose
the missing track; splice it back and grade the completed piece. Track-level infill (kin to gaptask).

## Pipeline (pkg-native)
1. **build_cases** (`build_cases.py`) — PURE track removal (corpus untouched): mask one voice by ROLE, write
   `<cid>_context.txt` (piece minus voice) + `<cid>_answer.txt` (voice alone, held-out). Role-balanced;
   lossless (context+answer == original); drum cases require a real KIT (kick+snare).
2. **measure** (`measure.py`) — splice a generated track back, grade the COMPLETED piece:
   - bass/harmony: PROXIMITY — fingerprint beat% of completed vs ORIGINAL (gaptask 39-axis), + in-key + fit.
   - drums: GROOVE — kit coverage + onset density + onset-position similarity to the real groove
     (percussion is ~invisible to the pitch fingerprint, so proximity is not used for drums).
   - non-copy vs the held-out real track.
3. **loop** (`loop/batch.py` + `accompaniment_loop/`) — Dockerized parallel: context + role brief -> agent
   writes ONLY that voice -> grade -> role-aware feedback -> keep best. Resume, crash isolation, BYO auth.

    python -m libretto.tasks.accompaniment.build_cases --n 20 --seed 1
    ./accompaniment_loop/run.sh --parallel 11 --rounds 3 --model opus

## Validated
Oracle (splice the REAL track back): bass/harmony beat% 100, d~0, improved; drums groove_fit True, rhythm_sim
1.0. Loop wires end-to-end. NOTE: contexts are full multi-voice songs (~70k-char prompt) — use a strong model
(Opus); Haiku returns empty on that size. An `--excerpt`-style shorter context would make generation easier.

## Contract
Removal is PURE (corpus untouched); cases in a separate dir. Tests: `libretto/tests/test_accompaniment.py`.
