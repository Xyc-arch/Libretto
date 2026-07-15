#!/usr/bin/env python3
"""loop_benefit.py — the 33-case loop-benefit demo (3 models x 11 genres).

For each model's seed-0 run it reports, per genre, the FIRST draft (r1) vs the loop's BEST, so the
"does the refinement loop help?" question is answered uniformly across model tiers. Scores are recomputed
from the drafts on disk (local, free — no claude -p tokens), so it works on archived runs.

Sources (auto-detected):
  newgen_loop/archive/<model>_seed0/<genre>/          <- archive a finished run here before the next model
  newgen_loop/state/<genre>/seed_0/                   <- the LIVE (possibly partial) run, labeled "live"

  python newgen_loop/loop_benefit.py                  # all detected models
"""
import json
import sys
from pathlib import Path

PROJ = Path(__file__).resolve().parents[4]     # repo root
sys.path.insert(0, str(PROJ))
from libretto.tasks.newgen.loop.feedback import compose_feedback          # noqa: E402

STATE = PROJ / "newgen_loop" / "state"          # results live at the deploy dir, not in the package
ARCHIVE = PROJ / "newgen_loop" / "archive"
GENRES = ["blues_gospel", "classical", "electronic_dance", "folk_country", "funk_soul_rnb",
          "hiphop_rap", "jazz", "latin", "metal", "pop_rock", "reggae_ska"]


def _rounds(wd, genre):
    """Re-score the c_r*.txt drafts in a working dir -> list of round records (skip empty/sentinel)."""
    out = []
    for r in range(1, 6):
        p = wd / f"c_r{r}.txt"
        if not (p.exists() and p.stat().st_size > 0):
            continue
        try:
            _, _, info = compose_feedback(p, genre)
        except Exception:  # noqa: BLE001
            continue
        if info["n_extreme"] == 99:
            continue
        info["round"] = r
        info["_score"] = (0 if info["is_target"] else 100) + info["n_extreme"]
        out.append(info)
    return out


def _model_dir(model, genre):
    if model == "live":
        return STATE / genre / "seed_0"
    return ARCHIVE / f"{model}_seed0" / genre


def _detect_models():
    models = [d.name[:-6] for d in sorted(ARCHIVE.glob("*_seed0")) if d.is_dir()]
    if any((STATE / g / "seed_0").exists() for g in GENRES):
        models.append("live")
    return models


def report(model):
    rows, deltas, improved, on_tgt, conv, iterated = [], [], 0, 0, 0, 0
    for g in GENRES:
        rs = _rounds(_model_dir(model, g), g)
        if not rs:
            continue
        r1 = rs[0]
        best = min(rs, key=lambda x: x["_score"])
        d = best["n_extreme"] - r1["n_extreme"]
        rows.append((g, len(rs), r1["n_extreme"], best["n_extreme"], d, best["is_target"], best["round"]))
        if len(rs) >= 2:
            iterated += 1
            deltas.append(d)
            improved += d < 0
        on_tgt += best["is_target"]
        conv += best["is_target"] and best["n_extreme"] <= 2
    print(f"\n===== {model.upper()} =====")
    print(f"{'genre':16} {'rounds':>6} {'r1ext':>6} {'bestext':>8} {'Δ':>4} {'on-tgt':>7} best@")
    for g, n, e1, eb, d, t, br in rows:
        print(f"{g:16} {n:>6} {e1:>6} {eb:>8} {d:>+4} {'Y' if t else '.':>7} r{br}")
    mean = (sum(deltas) / len(deltas)) if deltas else 0.0
    print(f"  cases {len(rows)}/11 | iterated(≥2 rounds) {iterated} | mean Δext(iterated) {mean:+.1f} "
          f"| improved {improved}/{iterated} | best on-target {on_tgt}/{len(rows)} | converged(≤2) {conv}/{len(rows)}")
    return dict(model=model, cases=len(rows), iterated=iterated, mean_delta=mean,
                improved=improved, on_target=on_tgt, converged=conv)


def main():
    models = _detect_models()
    if not models:
        print("no model runs found (archive/<model>_seed0 or state/*/seed_0)")
        return
    summ = [report(m) for m in models]
    print("\n===== 33-CASE SUMMARY (loop benefit across models) =====")
    print(f"{'model':10} {'cases':>5} {'iterated':>8} {'meanΔext':>9} {'improved':>9} {'on-target':>10} {'converged':>10}")
    for s in summ:
        print(f"{s['model']:10} {s['cases']:>5} {s['iterated']:>8} {s['mean_delta']:>+9.1f} "
              f"{str(s['improved'])+'/'+str(s['iterated']):>9} "
              f"{str(s['on_target'])+'/'+str(s['cases']):>10} {str(s['converged'])+'/'+str(s['cases']):>10}")


if __name__ == "__main__":
    main()
