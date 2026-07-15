#!/usr/bin/env python3
"""loop_benefit — does the refine loop help morph? Scores single-shot (round 1) vs the loop-picked best for
every case in a batch and reports the delta on morph_score + both lenses. Pure metrics (no agent).

    python -m libretto.tasks.morph.loop.loop_benefit \
        --cases compositions/morph/cases --state morph_loop/state

The loop MAXIMIZES morph_score (graduality x genre_shift), so the expected signal is: all three rise, with
the largest lift where morph_feedback bites (usually genre_shift, since the corrections name the target-genre
traits to bring in / source traits to fade).
"""
import argparse
import json
import os
import statistics as st
from pathlib import Path

from libretto.tasks.morph.morph_metric import morph_metric


def loop_benefit(cases_dir, state_dir):
    """Return (summary, per_case_rows). Re-scores each case's round-1 draft and compares to its loop-best
    (metric.json). Only counts cases that have both r1.txt and metric.json on disk."""
    cases_dir, state_dir = Path(cases_dir), Path(state_dir)
    cases = json.loads((cases_dir / "cases.json").read_text())
    rows = []
    for cid, c in cases.items():
        wd = state_dir / cid
        r1, mj = wd / "r1.txt", wd / "metric.json"
        if not (r1.exists() and mj.exists()):
            continue
        ss = morph_metric(str(r1), c["A"], c["B"], c["S"], source_genre=c["genreA"],
                          target_genre=c["genreB"], tmp_dir=str(wd / "_lb_segs"))
        lb = json.loads(mj.read_text())
        n_rounds = len(list(wd.glob("r*.txt")))
        rows.append(dict(case=cid, genreA=c["genreA"], genreB=c["genreB"], n_rounds=n_rounds,
                         ss_score=ss["morph_score"], lb_score=lb["morph_score"],
                         ss_grad=ss["graduality"]["score"], lb_grad=lb["graduality"]["score"],
                         ss_shift=ss["genre_shift"]["score"], lb_shift=lb["genre_shift"]["score"],
                         improved=lb["morph_score"] > ss["morph_score"] + 1e-9))
    n = len(rows)

    def _m(key):
        return round(st.mean([r[key] for r in rows]), 3) if rows else None

    summary = dict(
        n=n,
        score_single_shot=_m("ss_score"), score_loop_best=_m("lb_score"),
        score_delta=round((_m("lb_score") or 0) - (_m("ss_score") or 0), 3) if rows else None,
        graduality_single_shot=_m("ss_grad"), graduality_loop_best=_m("lb_grad"),
        genre_shift_single_shot=_m("ss_shift"), genre_shift_loop_best=_m("lb_shift"),
        improved=sum(r["improved"] for r in rows),
        converged_round1=sum(1 for r in rows if r["n_rounds"] == 1),
    )
    return summary, rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cases", default=os.environ.get("MORPH_CASES") or "compositions/morph/cases")
    ap.add_argument("--state", default=os.environ.get("MORPH_STATE") or "morph_loop/state")
    ap.add_argument("--out", default="", help="optional path to write the summary JSON")
    a = ap.parse_args()
    s, rows = loop_benefit(a.cases, a.state)
    print(f"n={s['n']}  ({s['converged_round1']} converged at round 1)")
    print(f"morph_score:  single-shot {s['score_single_shot']}  ->  loop-best {s['score_loop_best']}"
          f"   (delta {s['score_delta']:+})")
    print(f"graduality:   single-shot {s['graduality_single_shot']}  ->  loop-best {s['graduality_loop_best']}")
    print(f"genre_shift:  single-shot {s['genre_shift_single_shot']}  ->  loop-best {s['genre_shift_loop_best']}")
    print(f"improved: {s['improved']}/{s['n']} cases")
    if a.out:
        Path(a.out).write_text(json.dumps({"summary": s, "rows": rows}, indent=2))
        print(f"-> {a.out}")


if __name__ == "__main__":
    main()
