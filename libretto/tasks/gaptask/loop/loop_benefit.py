#!/usr/bin/env python3
"""loop_benefit — does the refine loop help gaptask? Grades single-shot (round 1) vs the loop-picked best for
every case in a batch and reports the delta on the composition gate + proximity. Pure metrics (no agent).

    python -m libretto.tasks.gaptask.loop.loop_benefit \
        --cases paper_data/gaptask_v3/cases --state gaptask_loop/state

The loop optimizes the GATE (compose in-character / non-degenerate / conditioned-reprise), so the expected,
honest signal is: gate-pass rises, while beat% (proximity to the often-reprise-heavy real answer) may fall —
the reconstruct-vs-compose tension. Reports both.
"""
import argparse
import json
import os
import statistics as st
from pathlib import Path

from libretto.tasks.gaptask.refine_loop import final_grade


def loop_benefit(cases_dir, state_dir):
    """Return (summary_dict, per_case_rows). Compares round-1 (single-shot) to best.txt (loop-best) via
    final_grade for every case that has both on disk."""
    cases_dir, state_dir = Path(cases_dir), Path(state_dir)
    cases = json.loads((cases_dir / "cases.json").read_text())
    rows = []
    for cid, c in cases.items():
        wd = state_dir / cid
        r1, best = wd / "r1.txt", wd / "best.txt"
        if not (r1.exists() and best.exists()):
            continue
        nbr = [s for s, _ in c["neighbors"]]
        common = dict(genre=c["genre"], neighbor_ids=nbr, region_type=c["type"])
        g1 = final_grade(str(r1), str(cases_dir / c["real"]), str(cases_dir / c["ctx"]), **common)
        gb = final_grade(str(best), str(cases_dir / c["real"]), str(cases_dir / c["ctx"]), **common)
        rows.append(dict(case=cid, genre=c["genre"], gap_type=c["type"],
                         ss_gate=bool(g1["gate_pass"]), lb_gate=bool(gb["gate_pass"]),
                         ss_beat=g1["beat_pct"], lb_beat=gb["beat_pct"],
                         picked_later=(best.read_text() != r1.read_text())))
    n = len(rows)
    ss_gate = sum(r["ss_gate"] for r in rows); lb_gate = sum(r["lb_gate"] for r in rows)
    ss_beat = [r["ss_beat"] for r in rows]; lb_beat = [r["lb_beat"] for r in rows]
    summary = dict(
        n=n,
        gate_single_shot=ss_gate, gate_loop_best=lb_gate, gate_delta=lb_gate - ss_gate,
        beat_single_shot=round(st.mean(ss_beat), 1) if ss_beat else None,
        beat_loop_best=round(st.mean(lb_beat), 1) if lb_beat else None,
        beat_delta=round(st.mean(lb_beat) - st.mean(ss_beat), 1) if ss_beat else None,
        picked_later=sum(r["picked_later"] for r in rows),
    )
    return summary, rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cases", default=os.environ.get("GAPTASK_CASES") or "paper_data/gaptask_v3/cases")
    ap.add_argument("--state", default=os.environ.get("GAPTASK_STATE") or "gaptask_loop/state")
    ap.add_argument("--out", default="", help="optional path to write the summary JSON")
    a = ap.parse_args()
    s, rows = loop_benefit(a.cases, a.state)
    print(f"n={s['n']}")
    print(f"GATE-PASS:  single-shot {s['gate_single_shot']}/{s['n']}  ->  loop-best {s['gate_loop_best']}/{s['n']}"
          f"   (delta +{s['gate_delta']})")
    print(f"mean beat%: single-shot {s['beat_single_shot']}  ->  loop-best {s['beat_loop_best']}"
          f"   (delta {s['beat_delta']:+})")
    print(f"loop picked a non-round-1 draft in {s['picked_later']}/{s['n']} cases")
    if a.out:
        Path(a.out).write_text(json.dumps({"summary": s, "rows": rows}, indent=2))
        print(f"-> {a.out}")


if __name__ == "__main__":
    main()
