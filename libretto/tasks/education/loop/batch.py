#!/usr/bin/env python3
"""batch.py - Dockerized education DRILL-COMPOSING loop (parallel).

Builds N advanced, comprehensive-by-default practice-drill specs, then for each drill a Claude Code agent
(`claude -p`) composes a single-voice piano grammar -> education `measure` gates it (single-channel, in-key,
challenge exercised, requirements, novelty) -> corrective feedback -> regenerate (<= rounds, pick best) ->
render MIDI. Same BYO-auth `claude -p` harness as the newgen/gaptask/morph/accompaniment loops.

    python -m libretto.tasks.education.loop.batch --n 24 --rounds 3 --parallel 12 --model opus
"""
import os
import sys
import json
import argparse
import statistics as st
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

PROJ = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJ))

from libretto.tasks.education.refine_loop import RefinementLoop                 # noqa: E402
from libretto.tasks.education.curriculum import autoscale                       # noqa: E402
from libretto.tasks.newgen.loop.generator import ClaudeCodeGenerator           # noqa: E402
from libretto.tasks.newgen.loop.runlog import RunLog                           # noqa: E402
from libretto.core import grammar_to_midi                                       # noqa: E402

STATE = Path(os.environ.get("EDU_STATE") or (PROJ / "education_loop" / "state"))
LOG = None

# Coherent advanced (key, scale-concept) pairs: the key and the SCALE challenge agree, so the in-key gate and
# the scale drill don't fight. Harmonic/melodic minor carry the advanced flavour (aug-2nd, raised 6/7).
KEY_SCALE = [
    ("D harmonic minor", "TS-HARMONIC-MINOR"), ("A harmonic minor", "TS-HARMONIC-MINOR"),
    ("E harmonic minor", "TS-HARMONIC-MINOR"), ("G harmonic minor", "TS-HARMONIC-MINOR"),
    ("C harmonic minor", "TS-HARMONIC-MINOR"), ("B harmonic minor", "TS-HARMONIC-MINOR"),
    ("F# harmonic minor", "TS-HARMONIC-MINOR"), ("C# harmonic minor", "TS-HARMONIC-MINOR"),
    ("D melodic minor", "TS-MELODIC-MINOR"), ("A melodic minor", "TS-MELODIC-MINOR"),
    ("G melodic minor", "TS-MELODIC-MINOR"), ("C melodic minor", "TS-MELODIC-MINOR"),
]


def build_specs(n):
    """N advanced comprehensive drill specs; key<->scale coherent, other devices auto-scaled per drill,
    variant cycles the tempo/meter ladders so the batch spans speeds and time signatures."""
    specs = []
    for i in range(n):
        key, scale = KEY_SCALE[i % len(KEY_SCALE)]
        others = autoscale("advanced", ["rhythm", "chord", "melody", "articulation"], n=4, offset=i)
        cids = [scale] + [c for c in others if c != scale][:4]
        specs.append(dict(level="advanced", key=key, concept_ids=cids, variant=i,
                          title=f"Advanced study {i + 1} in {key}"))
    return specs


def _run_one(i, spec, gen, rounds):
    label = f"drill_{i:02d}"
    wd = STATE / label
    best, rnds = RefinementLoop(gen, max_iter=rounds).run(spec, workdir=wd, label="practice")
    best_txt = Path(best["path"]).read_text()
    (wd / "best.txt").write_text(best_txt)
    (wd / "grade.json").write_text(json.dumps(best, indent=2, default=str))
    rendered = False
    try:
        grammar_to_midi.decode(str(wd / "best.txt"), str(wd / "best.mid")); rendered = True
    except Exception as e:  # noqa: BLE001
        print(f"[{label}] render FAILED: {e!r}", flush=True)
    row = dict(label=label, key=spec["key"], concepts=spec["concept_ids"], variant=spec["variant"],
               verdict=bool(best["verdict"]), score=best["score"], rounds=len(rnds),
               in_key=best.get("in_key"), out_of_scale=round(best.get("out_of_scale_frac", 0), 3),
               copy_vs_shown=round(best.get("copy_vs_shown", 0), 3), rendered=rendered)
    if LOG:
        LOG.event("drill", **{k: row[k] for k in ("label", "key", "variant", "verdict", "score", "rounds", "rendered")})
    print(f"[{label}] {spec['key']}: verdict={row['verdict']} score={row['score']} rounds={row['rounds']}", flush=True)
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=24)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--parallel", type=int, default=12)
    ap.add_argument("--model", default="opus")
    ap.add_argument("--timeout", type=int, default=0)
    ap.add_argument("--only", default="", help="comma-separated drill indices to (re)run, e.g. 3,7,11")
    a = ap.parse_args()
    jobs = list(enumerate(build_specs(a.n)))
    if a.only:
        keep = {int(x) for x in a.only.split(",") if x.strip() != ""}
        jobs = [(i, s) for i, s in jobs if i in keep]
    STATE.mkdir(parents=True, exist_ok=True)
    global LOG
    LOG = RunLog(STATE, model=a.model, proj=PROJ, params=dict(n=len(jobs), rounds=a.rounds, parallel=a.parallel, only=a.only))
    print(f"{len(jobs)} education drills | {a.parallel} parallel | rounds<= {a.rounds} | model {a.model}"
          f"{' | only ' + a.only if a.only else ''}", flush=True)
    gen = ClaudeCodeGenerator(model=a.model, timeout_s=(a.timeout or None))
    new_rows = []

    def _safe(i, spec):
        try:
            return _run_one(i, spec, gen, a.rounds)
        except Exception as e:  # noqa: BLE001
            print(f"[drill_{i:02d}] DRILL FAILED: {e!r}", flush=True); return None

    with ThreadPoolExecutor(max_workers=a.parallel) as pool:
        for f in as_completed([pool.submit(_safe, i, s) for i, s in jobs]):
            m = f.result()
            if m is not None:
                new_rows.append(m)

    # merge with any prior manifest so a partial (--only) re-run updates just those drills
    manifest = {}
    mf = STATE / "edu_manifest.json"
    if mf.exists():
        for r in json.loads(mf.read_text()).get("runs", []):
            manifest[r["label"]] = r
    for r in new_rows:
        manifest[r["label"]] = r
    manifest = list(manifest.values())
    passed = sum(1 for m in manifest if m["verdict"])
    summary = dict(n=len(manifest), passed=passed, pass_rate=round(passed / max(1, len(manifest)), 3),
                   rendered=sum(1 for m in manifest if m["rendered"]),
                   mean_score=round(st.mean([m["score"] for m in manifest]), 2) if manifest else None)
    (STATE / "edu_manifest.json").write_text(json.dumps({**summary, "runs": sorted(manifest, key=lambda r: r["label"])}, indent=2))
    if LOG:
        LOG.close(summary=summary)
    print(f"\nDONE: {len(manifest)} drills | passed {passed}/{len(manifest)} | rendered {summary['rendered']} -> {STATE}")


if __name__ == "__main__":
    main()
