# newgen_loop — Dockerized composition loop (axis-guided, agent-driven)

A self-improving **composition** loop: a Claude Code agent writes grammar, a deterministic evaluator
scores it against a target genre on the 39-axis coordinate system, and per-principle musical feedback
steers the next revision — until the piece reads as the target genre, stays in its plausible envelope,
and is novel. Same harness shape as `axis_evolve/` (Docker + `claude -p` + deterministic evaluator +
per-round feedback), but the evaluator scores a **composition against a target** instead of an axis set.

Reuses the existing task code (`libretto/tasks/newgen/refine_loop.py`, `retrieval.py`,
`libretto/core/{genre_band_check,axis_feedback,fingerprint,copy_risk}`) — the Docker layer adds the
agent-as-generator seam and the batch/disjoint-retrieval orchestration.

---

## Settled design decisions (baked in)

1. **Feedback = axes only.** No audiobox in the loop (redundant with P4-selected axes, expensive,
   low-actionability). Audiobox, if ever, is a *post-convergence selection/validation* stage, not steering.
2. **Percentile + genre-conditioned p5/p95 guardrail**, paired with a **classifier steer**:
   - *Guardrail:* flag axes beyond the **target genre's** p5/p95 (`genre_conditioned` bands) — extreme
     *for the genre*, not globally (metal SHOULD be extreme on `power_chord_ratio`).
   - *Steer:* the genre classifier says which axes make the draft read as the wrong genre.
   - Feedback is **all flagged axes, ranked** (severity × classifier importance), each **translated to a
     musical action** via `axis_feedback` (not raw numbers), plus the full 39-percentile profile as reference.
3. **Retrieval:** exemplars condition the agent (retrieval-augmented, +15pt in prior ablation).
   - *Per seed:* exclude the seed itself + its near-duplicates; diversify the k (MMR-style); novelty-check
     the output against the retrieved set (don't parrot what you were shown).
   - *Across seeds (batch):* dedup the pool, then assign **disjoint** exemplars — no corpus song is handed
     to two seeds (`retrieval.prototypical_songs(..., exclude=used)` threaded with a shared `used` set).
4. **Generator = Claude Code agent** (`claude -p`, no API key), authed from the mounted Keychain token —
   same as axis_evolve. Not `generation.ClaudeGenerator` (that's the API path).

---

## Loop (per seed)

```
target genre + seed
  → retrieve k exemplars   (exclude seed+near-dups+already-used-by-other-seeds; diversify)
  → agent composes grammar (conditioned on exemplars + concept block)
  → evaluate:
        P1  non-degeneracy / length gate
        P3  classifier: does it read as the target genre? which axes pull it wrong (ranked)
        P2  genre-conditioned p5/p95: axes outside the genre's plausible range (ranked, signed)
        novelty: copy_risk vs retrieved exemplars + corpus (below adaptive threshold)
  → feedback: ranked, musically-translated actions (axis_feedback)
  → agent revises        (≤ max_iter; keep best by fitness)
```

Batch = run S seeds, sharing the `used` exemplar set so retrieval stays disjoint across seeds.

---

## Components

| file | role |
|---|---|
| `Dockerfile` | python eval env + Node + Claude Code CLI (no torch — no audiobox). Mounts project RO, state RW. |
| `entrypoint.sh` | provision claude-code creds from `/opt/cc-auth`; run the batch loop |
| `run.sh` | refresh Keychain token → `docker run` with mounts + args (genre, seeds, k, rounds) |
| `generator.py` | `ClaudeCodeGenerator.generate(prompt, context) -> grammar_text` — shells `claude -p` (the axis_evolve `propose()` pattern), returns the grammar the agent wrote |
| `batch.py` | orchestrates S disjoint seeds → per-seed `refine_loop` → collect + audit |
| `composer_brief.md` | the agent prompt: grammar contract + "compose in genre X conditioned on these exemplars; act on the ranked axis feedback" |

Evaluator is `libretto.tasks.newgen.refine_loop` with two deltas:
- bands use **p5/p95** (guardrail) in addition to the existing p25/p75 dosage;
- add the **classifier-diagnosis** feedback line (predict genre from the 39-fp, rank misclassifying axes).

---

## Prerequisites (must land before this runs)
1. **Deploy the 39 axes** — `axes_v3.py` + rebuild `corpus_distribution.json` (global + genre_conditioned)
   + `corpus_fps.json`, so `metrics_for`, `fingerprint`, `genre_band_check`, and the classifier all use the 39.
2. **Update `axis_feedback.py`** — the axis→musical-instruction map keyed to the 39 (seed from docstrings).
3. **Near-dup map** — a dedup list for the retrieval pool (corpus has known near-duplicates).

---

## Outputs (host, via the mounted state volume)
```
newgen_loop/state/<genre>/seed_<n>/
    round_*.txt          each draft grammar
    round_*_feedback.txt the ranked musical feedback the agent saw
    best.txt             chosen draft (highest fitness)
    fitness.json         per-round fitness + fingerprint + classifier verdict + copy_risk
    exemplars.json       the disjoint retrieved set used
  batch_manifest.json    seeds, genres, disjointness check, convergence summary
```
Auditable per round like axis_evolve (prompt, agent output, evaluation all persisted).
