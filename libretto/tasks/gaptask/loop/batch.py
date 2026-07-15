#!/usr/bin/env python3
"""batch.py — Dockerized gaptask loop, PARALLEL. Regenerate a held-out region, BLIND, with a leakage-clean
refine loop, then grade against the real region.

For each case (11 genres x 3 gap-types): build a prompt from the visible CONTEXT + k neighbor IDs/tendencies
(never the answer) -> a Claude Code agent (claude -p) generates the region -> `region_fitness` scores it
(purely structural, leakage-clean) -> `dosage_feedback` corrects the next round (<= --rounds) -> keep the
best-by-fitness -> `final_grade` reports proximity beat% vs the held-out real region. Same claude -p / BYO-
auth harness as the newgen loop.

    python -m libretto.tasks.gaptask.loop.batch --parallel 11 --rounds 3 --model opus
"""
import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

PROJ = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJ))

from libretto.generation.interface import load_prompt, PROMPTS                 # noqa: E402
from libretto.tasks.gaptask.refine_loop import region_fitness, dosage_feedback, final_grade  # noqa: E402
from libretto.tasks.newgen.loop.generator import ClaudeCodeGenerator           # noqa: E402
from libretto.tasks.newgen.loop.runlog import RunLog                           # noqa: E402
import re                                                                       # noqa: E402

CASES = Path(os.environ.get("GAPTASK_CASES") or (PROJ / "paper_data/gaptask_v3/cases"))
STATE = Path(os.environ.get("GAPTASK_STATE") or (PROJ / "gaptask_loop" / "state"))
TMPL = load_prompt("gaptask")
SHARED = (PROMPTS / "_shared.md").read_text()
LOG = None


def _hv(hdr, tag):
    m = re.search(rf"{tag}:\s*([^|]+)", hdr)
    return m.group(1).strip() if m else ""


def build_prompt(case, ctx_text, corrections=None):
    context = dict(gap_type=case["type"], target_bars=case["target_bars"],
                   key=_hv(case["hdr"], "KEY"), meter=_hv(case["hdr"], "METER"), tempo=_hv(case["hdr"], "TEMPO"),
                   neighbor_tendencies=case["tend"], neighbor_ids=[s for s, _ in case["neighbors"]],
                   context_grammar=ctx_text)
    p = f"{TMPL}\n\n{SHARED}\n\n## CONTEXT (JSON)\n```json\n{json.dumps(context, indent=1)}\n```\n"
    if corrections:
        p += "\n## CORRECTIONS — act on ALL, regenerate the whole region\n" + "\n".join(corrections)
    return p


def _fallback_fit(tgt):
    """A COMPLETE fit dict for when a round can't be scored (e.g. the generator returned empty/garbage on a
    token-limit or auth blip). Must carry every key dosage_feedback + the pick-best _key read, so one bad
    round degrades gracefully instead of KeyError-ing the whole ThreadPool."""
    return {"score": 9999, "converged": False, "bars": 0, "target_bars": tgt, "len_err": tgt,
            "c1_pass": False, "c2_pass": False, "c1_extremes": [], "c1_budget": 99,
            "oob": [], "n_oob": 0, "copy_pass": True, "copy_risk": 0.0, "reprise": 0.0,
            "reprise_thr": 0.75, "plag_vs_corpus": 0.0, "D_ctx": 999.0}


def _run_one(job, gen, rounds):
    cid, case = job
    genre, tgt = case["genre"], case["target_bars"]
    ctx_path = CASES / case["ctx"]
    ctx_text = ctx_path.read_text()
    nbr = [s for s, _ in case["neighbors"]]
    wd = STATE / cid; wd.mkdir(parents=True, exist_ok=True)
    # CASE-LEVEL RESUME: a completed case already has grade.json — skip it (saves the Opus tokens on restart
    # after a crash/token-limit). Delete grade.json to force a re-run of a specific case.
    gj = wd / "grade.json"
    if gj.exists():
        try:
            g = json.loads(gj.read_text())
            print(f"[{cid}] resume: already graded (beat% {g.get('beat_pct')}) — skipping", flush=True)
            return dict(case=cid, genre=genre, gap_type=case["type"], beat_pct=g.get("beat_pct"),
                        D_gr=g.get("D_gr"), gate_pass=g.get("gate_pass"))
        except Exception:  # noqa: BLE001
            pass  # corrupt grade -> fall through and regenerate
    corrections, best = [], None
    for r in range(1, rounds + 1):
        try:
            grammar = gen.generate(build_prompt(case, ctx_text, corrections), {})
        except Exception as e:  # noqa: BLE001 — generator/auth/token failure must not kill the pool
            print(f"[{cid}] round {r}: generate FAILED ({e!r})", flush=True)
            grammar = ""
        p = wd / f"r{r}.txt"; p.write_text(grammar or "", encoding="utf-8")
        try:
            fit = region_fitness(str(p), str(ctx_path), genre=genre, target_bars=tgt, neighbor_ids=nbr,
                                 region_type=case["type"])
        except Exception:  # noqa: BLE001
            fit = _fallback_fit(tgt)
        rd = dict(round=r, path=str(p), **{k: v for k, v in fit.items() if k in
                  ("score", "converged", "bars", "c1_pass", "c2_pass", "copy_pass", "copy_risk", "D_ctx")})
        # HARD COPY GATE on the pick: a copy-passing round beats any copy-failing round regardless of
        # fitness — so we never SUBMIT a near-copy fill while a genuine one exists. Among same-gate rounds,
        # lower fitness wins. (Mirrors the newgen novelty-controlled best-pick.)
        def _key(f):
            return (0 if f.get("copy_pass") else 1, f["score"])
        if best is None or _key(fit) < _key(best["_fit"]):
            best = dict(path=str(p), _fit=fit)
        if LOG:
            LOG.event("round", case=cid, genre=genre, round=r, score=fit.get("score"),
                      bars=fit.get("bars"), converged=fit.get("converged"))
        print(f"[{cid}] round {r}: score {fit.get('score')} bars {fit.get('bars')}"
              f"{' | CONVERGED' if fit.get('converged') else ''}", flush=True)
        if fit.get("converged"):
            break
        try:
            corrections = dosage_feedback(fit)
        except Exception:  # noqa: BLE001 — a malformed fit must not stop the loop; retry with no correction
            corrections = []
    # write best + GROUND-TRUTH grade (post-loop, never fed back)
    (wd / "best.txt").write_text(Path(best["path"]).read_text(encoding="utf-8"), encoding="utf-8")
    grade = final_grade(best["path"], str(CASES / case["real"]), str(ctx_path), genre=genre, neighbor_ids=nbr,
                        region_type=case["type"])
    (wd / "grade.json").write_text(json.dumps(grade, indent=2, default=str))
    beat = grade.get("beat_pct")
    if LOG:
        LOG.event("grade", case=cid, genre=genre, gap_type=case["type"], beat_pct=beat,
                  D_gr=grade.get("D_gr"), gate_pass=grade.get("gate_pass"))
    print(f"[{cid}] GRADE beat% {beat} | D_gr {grade.get('D_gr')} | gate {grade.get('gate_pass')} "
          f"| copy {grade.get('copy_risk')}", flush=True)
    return dict(case=cid, genre=genre, gap_type=case["type"], beat_pct=beat,
                D_gr=grade.get("D_gr"), gate_pass=grade.get("gate_pass"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="", help="comma-separated case ids; empty = all")
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
    LOG = RunLog(STATE, model=a.model, proj=PROJ,
                 params=dict(n_cases=len(cases), rounds=a.rounds, parallel=a.parallel))
    print(f"{len(cases)} gaptask cases | {a.parallel} parallel agents | rounds<= {a.rounds} | model {a.model}",
          flush=True)
    print(f"[log] metrics -> {LOG.path}", flush=True)
    gen = ClaudeCodeGenerator(model=a.model, timeout_s=(a.timeout or None))
    manifest = []

    def _safe(job):
        try:
            return _run_one(job, gen, a.rounds)
        except Exception as e:  # noqa: BLE001 — isolate a case failure so it can't abort the whole batch
            print(f"[{job[0]}] CASE FAILED: {e!r}", flush=True)
            return None

    from concurrent.futures import as_completed
    with ThreadPoolExecutor(max_workers=a.parallel) as pool:
        futs = [pool.submit(_safe, j) for j in cases.items()]
        for f in as_completed(futs):
            m = f.result()
            if m is not None:
                manifest.append(m)

    beats = [m["beat_pct"] for m in manifest if m.get("beat_pct") is not None]
    gates = sum(1 for m in manifest if m.get("gate_pass"))
    import statistics as st
    (STATE / "gaptask_manifest.json").write_text(json.dumps(
        {"n": len(manifest), "mean_beat_pct": round(st.mean(beats), 1) if beats else None,
         "beat_gt_chance": sum(1 for b in beats if b > 50), "gate_pass": gates, "runs": manifest}, indent=2))
    LOG.close(summary=dict(n=len(manifest), mean_beat_pct=round(st.mean(beats), 1) if beats else None,
                           beat_gt_chance=sum(1 for b in beats if b > 50), gate_pass=gates))
    print(f"\nDONE: {len(manifest)} cases | mean beat% {round(st.mean(beats), 1) if beats else '-'} | "
          f"beat>chance {sum(1 for b in beats if b > 50)}/{len(beats)} | gate {gates}/{len(manifest)} -> {STATE}")


if __name__ == "__main__":
    main()
