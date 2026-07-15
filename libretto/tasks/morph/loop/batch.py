#!/usr/bin/env python3
"""batch.py — Dockerized MORPH loop, PARALLEL. Generate a stylistic cross-genre morph A -> B, score it with
morph_metric (graduality + genre-shift), refine, keep the best.

For each cross-genre case (11 genres in a balanced cycle): build a prompt from the case's per-segment axis
trajectory + genre plan -> a Claude Code agent (claude -p) composes the S-segment morph -> `morph_metric`
scores it (graduality: monotonic even glide A->B; genre-shift: classifier sees P(source) fall / P(target)
rise) -> `morph_feedback` corrects the next round -> keep the best-by-morph_score. Same claude -p / BYO-auth
harness as the gaptask + newgen loops.

    python -m libretto.tasks.morph.loop.batch --parallel 11 --rounds 3 --model opus
"""
import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

PROJ = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJ))

from libretto.generation.interface import load_prompt, PROMPTS                 # noqa: E402
from libretto.tasks.morph.morph_metric import morph_metric, AXES              # noqa: E402
from libretto.tasks.newgen.loop.generator import ClaudeCodeGenerator           # noqa: E402
from libretto.tasks.newgen.loop.runlog import RunLog                           # noqa: E402

CASES = Path(os.environ.get("MORPH_CASES") or (PROJ / "compositions/morph/cases"))
STATE = Path(os.environ.get("MORPH_STATE") or (PROJ / "morph_loop" / "state"))
TMPL = load_prompt("morph")
SHARED = (PROMPTS / "_shared.md").read_text()
LOG = None


def build_prompt(case, corrections=None):
    """A full-morph generation brief: the per-segment target trajectory on the morph axes + the genre/key/tempo
    plan + the two metric objectives (gradual even glide, genre crossing)."""
    ma = case["morph_axes"]
    traj = {a.split("_", 1)[1]: [case["targets"][s][a] for s in range(case["S"])] for a in ma}
    context = dict(
        source_genre=case["genreA"], target_genre=case["genreB"],
        segments=case["S"], bars_per_segment=case["seg_bars"], total_bars=case["total_bars"],
        key_A=case["keyA"], key_B=case["keyB"], tempo_A=case["tempoA"], tempo_B=case["tempoB"],
        morph_axis_trajectory_percentiles=traj,
    )
    obj = (f"Compose a {case['S']}-segment morph ({case['seg_bars']} bars each = {case['total_bars']} bars) that "
           f"travels from {case['genreA']} to {case['genreB']}. TWO objectives: (1) GRADUAL — each segment moves "
           f"EVENLY toward the target on the axes in `morph_axis_trajectory_percentiles` (segment s should hit "
           f"roughly its listed percentile); no jumps, no backtracking. (2) GENRE SHIFT — segment 1 should read "
           f"as {case['genreA']}, the last as {case['genreB']}, crossing over near the middle. Reconcile key "
           f"{case['keyA']}->{case['keyB']} and tempo {case['tempoA']}->{case['tempoB']} across the glide. Output "
           f"ONLY the morph grammar ({case['total_bars']} bars).")
    p = f"{TMPL}\n\n{SHARED}\n\n## OBJECTIVE\n{obj}\n\n## CONTEXT (JSON)\n```json\n{json.dumps(context, indent=1)}\n```\n"
    if corrections:
        p += "\n## CORRECTIONS — act on ALL, regenerate the WHOLE morph\n" + "\n".join(corrections)
    return p


def morph_feedback(r):
    """Turn a morph_metric result into corrections for the next round. Pure function of the metric (which never
    sees a held-out answer — morphs have none). Targets the two lenses that scored low."""
    g, s = r["graduality"], r["genre_shift"]
    lines = []
    if not g["anchored"]:
        lines.append(f"ANCHORS: start progress={g['progress'][0]:.2f} (want <0.40, sound like {s['source_genre']}), "
                     f"end progress={g['progress'][-1]:.2f} (want >0.60, sound like {s['target_genre']}). Push the "
                     f"first segment closer to the source and the last closer to the target.")
    if g["backtracks"]:
        lines.append(f"MONOTONIC: {g['backtracks']} segment(s) moved BACKWARD toward the source. Every segment "
                     f"must progress further toward {s['target_genre']} than the one before.")
    if g["max_jolt"] and g["max_jolt"] > 2.0:
        lines.append(f"EVEN STEPS: one segment jumps {g['max_jolt']:.1f}x the ideal step — too abrupt. Spread the "
                     f"change evenly across all {r['S']} segments (a smooth ramp, not a jump-cut).")
    if not s["same_genre"]:
        if s["target_rise_spearman"] < 0.5:
            lines.append(f"GENRE (target): P({s['target_genre']}) is not rising across the morph. Bring in "
                         f"{s['target_genre']}-defining traits progressively in the later segments.")
        if s["source_fall_spearman"] > -0.5:
            lines.append(f"GENRE (source): P({s['source_genre']}) is not fading. Reduce {s['source_genre']} "
                         f"characteristics in the later segments.")
        if s["crossover_seg"] is None:
            lines.append(f"CROSSOVER: the morph never crosses from {s['source_genre']} to {s['target_genre']}. "
                         f"By the final segments {s['target_genre']} must dominate.")
    if not r["genuinely_new"]:
        lines.append("NOVELTY: the morph copies too much real material — invent fresh transitional material, "
                     "do not splice A's and B's actual notes.")
    return lines


def _run_one(job, gen, rounds):
    cid, case = job
    A, B, S = case["A"], case["B"], case["S"]
    wd = STATE / cid; wd.mkdir(parents=True, exist_ok=True)
    mj = wd / "metric.json"
    if mj.exists():                                    # case-level resume (skip completed on restart)
        try:
            m = json.loads(mj.read_text())
            print(f"[{cid}] resume: already scored (morph_score {m.get('morph_score')}) — skipping", flush=True)
            return dict(case=cid, genreA=case["genreA"], genreB=case["genreB"], **_summ(m))
        except Exception:  # noqa: BLE001
            pass
    corrections, best = [], None
    for r in range(1, rounds + 1):
        try:
            grammar = gen.generate(build_prompt(case, corrections), {})
        except Exception as e:  # noqa: BLE001
            print(f"[{cid}] round {r}: generate FAILED ({e!r})", flush=True); grammar = ""
        p = wd / f"r{r}.txt"; p.write_text(grammar or "", encoding="utf-8")
        try:
            res = morph_metric(str(p), A, B, S, source_genre=case["genreA"], target_genre=case["genreB"],
                               tmp_dir=str(wd / "_segs"))
        except Exception as e:  # noqa: BLE001
            res = dict(morph_score=-1.0, verdict=False, graduality=dict(score=0), genre_shift=dict(score=0),
                       genuinely_new=False)
        # keep the HIGHEST morph_score (morph is a maximize objective, unlike gaptask's min-fitness)
        if best is None or res.get("morph_score", -1) > best["morph_score"]:
            best = dict(path=str(p), **res)
        sc = res.get("morph_score", -1)
        if LOG:
            LOG.event("round", case=cid, round=r, morph_score=sc,
                      graduality=res.get("graduality", {}).get("score"),
                      genre_shift=res.get("genre_shift", {}).get("score"))
        print(f"[{cid}] round {r}: morph_score {sc} "
              f"(grad {res.get('graduality',{}).get('score')} shift {res.get('genre_shift',{}).get('score')})"
              f"{' | PASS' if res.get('verdict') else ''}", flush=True)
        if res.get("verdict"):
            break
        corrections = morph_feedback(res)
    (wd / "best.txt").write_text(Path(best["path"]).read_text(encoding="utf-8"), encoding="utf-8")
    best_clean = {k: v for k, v in best.items() if k != "path"}
    mj.write_text(json.dumps(best_clean, indent=2, default=str))
    print(f"[{cid}] BEST morph_score {best['morph_score']} | verdict {best.get('verdict')} "
          f"| {case['genreA']} -> {case['genreB']}", flush=True)
    if LOG:
        LOG.event("best", case=cid, genreA=case["genreA"], genreB=case["genreB"], **_summ(best))
    return dict(case=cid, genreA=case["genreA"], genreB=case["genreB"], **_summ(best))


def _summ(m):
    return dict(morph_score=m.get("morph_score"), verdict=bool(m.get("verdict")),
                graduality=(m.get("graduality") or {}).get("score"),
                genre_shift=(m.get("genre_shift") or {}).get("score"),
                genuinely_new=m.get("genuinely_new"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="", help="comma-separated cids; empty = all")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--parallel", type=int, default=11)
    ap.add_argument("--model", default="opus")
    ap.add_argument("--timeout", type=int, default=0)
    a = ap.parse_args()
    cases = json.loads((CASES / "cases.json").read_text())
    if a.cases:
        want = {c.strip() for c in a.cases.split(",")}
        cases = {k: v for k, v in cases.items() if k in want}
    STATE.mkdir(parents=True, exist_ok=True)
    global LOG
    LOG = RunLog(STATE, model=a.model, proj=PROJ, params=dict(n_cases=len(cases), rounds=a.rounds, parallel=a.parallel))
    print(f"{len(cases)} cross-genre morph cases | {a.parallel} parallel | rounds<= {a.rounds} | model {a.model}",
          flush=True)
    print(f"[log] metrics -> {LOG.path}", flush=True)
    gen = ClaudeCodeGenerator(model=a.model, timeout_s=(a.timeout or None))
    manifest = []

    def _safe(job):
        try:
            return _run_one(job, gen, a.rounds)
        except Exception as e:  # noqa: BLE001
            print(f"[{job[0]}] CASE FAILED: {e!r}", flush=True); return None

    with ThreadPoolExecutor(max_workers=a.parallel) as pool:
        for f in as_completed([pool.submit(_safe, j) for j in cases.items()]):
            m = f.result()
            if m is not None:
                manifest.append(m)

    import statistics as st
    scores = [m["morph_score"] for m in manifest if m.get("morph_score") is not None]
    passes = sum(1 for m in manifest if m.get("verdict"))
    summary = dict(n=len(manifest), mean_morph_score=round(st.mean(scores), 3) if scores else None,
                   mean_graduality=round(st.mean([m["graduality"] for m in manifest if m.get("graduality") is not None]), 3) if manifest else None,
                   mean_genre_shift=round(st.mean([m["genre_shift"] for m in manifest if m.get("genre_shift") is not None]), 3) if manifest else None,
                   verdict_pass=passes, runs=manifest)
    (STATE / "morph_manifest.json").write_text(json.dumps(summary, indent=2))
    LOG.close(summary={k: v for k, v in summary.items() if k != "runs"})
    print(f"\nDONE: {len(manifest)} morphs | mean morph_score {summary['mean_morph_score']} "
          f"(grad {summary['mean_graduality']} shift {summary['mean_genre_shift']}) | "
          f"verdict-pass {passes}/{len(manifest)} -> {STATE}")


if __name__ == "__main__":
    main()
