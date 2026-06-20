#!/usr/bin/env python3
"""gaptask_channel_check.py — INTEGRITY check for the gap-task: is the generated region's note-overlap
with the held-out REAL answer innocent (coincidental continuation of the visible context) or leakage?

The generator is provably blind to the real region (its brief = context + neighbor IDs/tendencies +
target_bars + KB; it never receives the real-region file). So overlap with the answer must come from one
of two innocent sources: (a) reprise of the VISIBLE CONTEXT that the real answer also contains, or (b)
coincidental same-song/idiom vocabulary. This tool quantifies the split per case:
  overlap        = gen-region notes (bar,onset,pitch) that coincide with the held-out real region.
  context-explained (INNOCENT) = overlap notes whose (onset-in-bar, pitch) is ALSO present in the context.
  unique-to-answer = the rest (matches the answer but not in the visible context — coincidental, since blind).

Verdict for the project: if context-explained ≈ 100%, the elevated answer-overlap is verified coincidental
continuation of visible context (NOT leakage), and no cases need exclusion.

  python3 gaptask_channel_check.py [compositions/holdout42 | compositions/gaptask21]
"""
import json, sys
from pathlib import Path
from .understanding_probe import Song

def reg_notes(p): return set((e["bar"], round(e["onb"], 2), e["midi"]) for e in Song(p).events)
def ctx_pos(p):   return set((round(e["onb"], 2), e["midi"]) for e in Song(p).events)

def run(d):
    d = Path(d); cases = json.loads((d/"cases.json").read_text()); rows = []
    for cid, c in cases.items():
        gp = d/f"{cid}_gen.txt"
        if not gp.exists(): continue
        gen = reg_notes(gp); real = reg_notes(d/c["real"]); ctx = ctx_pos(d/c["ctx"])
        if not gen: continue
        ov = gen & real; rate = len(ov)/len(gen)
        inn = (sum(1 for (b,o,m) in ov if (o,m) in ctx)/len(ov)) if ov else 1.0
        rows.append((cid, rate, len(ov), inn))
    import statistics as st
    print(f"=== {d.name} (n={len(rows)}) ===")
    print(f"  mean answer-overlap {st.mean(r[1] for r in rows):.2f} | mean context-explained(innocent) {st.mean(r[3] for r in rows):.2f}")
    elev = sorted([r for r in rows if r[1] >= 0.30], key=lambda x: -x[1])
    print(f"  elevated (overlap≥0.30): {len(elev)}; all innocent% = {[round(r[3]*100) for r in elev]}")
    worst = max(rows, key=lambda x: (1-x[3])*x[1])
    print(f"  worst unique-weighted: {worst[0]} overlap {worst[1]:.2f}, unique {(1-worst[3])*100:.0f}% "
          f"({int(worst[2]*(1-worst[3]))} of {worst[2]} notes)")
    leak = [r for r in rows if (1-r[3]) > 0.10 and r[1] >= 0.20]
    print(f"  >>> {'CLEAN — answer-overlap is context-explained reprise, not leakage' if not leak else 'FLAG (exclude): '+str([r[0] for r in leak])}")
    return rows

if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "compositions/holdout42")
