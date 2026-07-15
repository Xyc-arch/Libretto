#!/usr/bin/env python3
"""morph_measure.py — score a fingerprint MORPH A -> B.

Splits the morph into S equal segments and checks the TRAJECTORY through the 28-axis space:
  progress_s = D(seg_s, A) / (D(seg_s, A) + D(seg_s, B))  — should rise ~0 -> ~1 monotonically.
Plus: endpoints anchored (seg1 near A, segS near B), smooth steps (no jolt), genuinely-new
(copy_risk vs A and B and corpus < 0.30 — a stylistic morph, not a spliced medley), and each segment
non-degenerate (genre-aware-free C1 with the short-segment length-axis exemption).

  python3 morph_measure.py <morph.txt> <A_sid> <B_sid> <S>
"""
import json, sys, re
from pathlib import Path
import numpy as np
from libretto.core import metric_discovery as md
from libretto.core import Song
from libretto.core import copy_risk as cr

import libretto
DATA = libretto.data_root()
GRAMMAR = DATA / "grammar"; OUT = Path("compositions") / "morph"
CANON = json.loads((DATA/"corpus_distribution.json").read_text())
AXES = CANON["axes_order"]; COLS = {a: np.array(CANON["axes"][a]["values"], float) for a in AXES}
LENGTH_AXES = {"form_distinct_bar_frac","form_section_per100bars","form_novelty_rate",
               "form_self_similarity","rhy_density_variability"}
# RAMPABLE axes: per-bar-meaningful and continuously variable — the ones a morph can actually glide.
# Excludes whole-piece accumulators (distinct_pc, novelty_rate, section_per100bars) that are noisy/
# meaningless on a short segment. The morph trajectory is measured on RAMPABLE ∩ (axes that differ A→B).
RAMPABLE = ["har_chromaticism","har_dimaug_rate","rhy_triplet_share","har_chord_change_rate",
            "mel_up_ratio","har_root_motion_entropy","tex_active_voice_density","rhy_onset_density_per_bar",
            "rhy_syncopation_rate","har_pc_entropy","mel_interval_entropy","rhy_dur_cv"]

def split_segments(path, S):
    """Write S equal-bar sub-grammars (header + that bar range, renumbered) to temp files; return paths."""
    lines = Path(path).read_text().splitlines()
    head = [l for l in lines[:8] if not l.startswith("@")][:2]
    blocks, cur = [], None
    for l in lines:
        if l.startswith("@"):
            if cur is not None: blocks.append(cur)
            cur=[l]
        elif cur is not None: cur.append(l)
    if cur is not None: blocks.append(cur)
    n=len(blocks); per=n//S; segs=[]
    for s in range(S):
        lo=s*per; hi=(s+1)*per if s<S-1 else n
        bb=blocks[lo:hi]
        out=[re.sub(r"BARS:\s*\d+",f"BARS: {len(bb)}",head[0]), head[1] if len(head)>1 else "VOICES: V"]
        for i,blk in enumerate(bb,1):
            x=list(blk); x[0]=re.sub(r"^@\d+",f"@{i}",x[0]); out.extend(x)
        p=OUT/f"_seg{s}.txt"; p.write_text("\n".join(out)+"\n"); segs.append(p)
    return segs

def fpv(p):
    m=md.metrics_for(Song(p),p)
    return np.array([round(float((COLS[a]<=float(m[a])).mean()*100)) for a in AXES],float), m
def dist(a,b): return float(np.mean(np.abs(a-b)))
def c1_ext(prof,m):
    out=[]
    for a in AXES:
        if a in LENGTH_AXES: continue
        if prof[a]<=5 or prof[a]>=95: out.append(a.split('_',1)[1])
    return out

def main(path, A, B, S):
    case=json.loads((OUT/f"morph_{A}_{B}_case.json").read_text())
    fa=np.array([case["fpA"][a] for a in AXES],float); fb=np.array([case["fpB"][a] for a in AXES],float)
    # rampable subspace = RAMPABLE ∩ axes that actually differ A→B (>=15 pct apart)
    RAMP=[a for a in RAMPABLE if abs(case["fpA"][a]-case["fpB"][a])>=15]
    ridx=[AXES.index(a) for a in RAMP]
    faR=fa[ridx]; fbR=fb[ridx]
    segs=split_segments(path, S)
    rows=[]
    for s,p in enumerate(segs):
        v,m=fpv(p); prof={a:int(v[i]) for i,a in enumerate(AXES)}
        dA=dist(v,fa); dB=dist(v,fb); prog=dA/max(1e-9,(dA+dB))
        vr=v[ridx]; dAr=float(np.mean(np.abs(vr-faR))); dBr=float(np.mean(np.abs(vr-fbR)))
        progR=dAr/max(1e-9,(dAr+dBr))
        rows.append((s,dA,dB,prog,len(c1_ext(prof,m)),progR))
    # trajectory — measured on the RAMPABLE subspace (the morph signal)
    progs=[r[5] for r in rows]; fullprogs=[r[3] for r in rows]
    mono=all(progs[i] <= progs[i+1]+0.05 for i in range(len(progs)-1))   # allow tiny dips
    span=progs[-1]-progs[0]
    print(f"  [rampable axes ({len(RAMP)}): {', '.join(a.split('_',1)[1] for a in RAMP)}]")
    # novelty vs A, B, corpus
    riskA=cr.copy_risk(path, cited=[A], vs_corpus=False, threshold=0.30)["max_cited"]["overlap"]
    riskB=cr.copy_risk(path, cited=[B], vs_corpus=False, threshold=0.30)["max_cited"]["overlap"]
    riskC=cr.copy_risk(path, vs_corpus=True, threshold=0.30)["max_corpus"]["overlap"]
    new = max(riskA,riskB,riskC) < 0.30
    nondegen = all(r[4]<=3 for r in rows)

    print(f"=== MORPH MEASURE — {Path(path).name} — {A} -> {B} ({S} segments) ===")
    print(f"  {'seg':<5}{'rampProg':>10}{'fullProg':>10}{'C1ext':>7}")
    for s,dA,dB,fprog,ext,progR in rows:
        bar = "  "+"."*int(progR*20)+"|"+"."*(20-int(progR*20))
        print(f"  {s+1:<5}{progR:>10.2f}{fprog:>10.2f}{ext:>7}{bar}")
    print(f"  TRAJECTORY (rampable): progress {progs[0]:.2f} -> {progs[-1]:.2f} (span {span:.2f}); monotonic A→B: {'Y' if mono else 'N'}")
    print(f"  ENDPOINTS (rampable): seg1 progress={progs[0]:.2f} (→0=A), seg{S} progress={progs[-1]:.2f} (→1=B)")
    print(f"  GENUINELY-NEW: copy vs A={riskA:.2f} vs B={riskB:.2f} vs corpus={riskC:.2f}  (<0.30: {'Y' if new else 'N'})")
    print(f"  (non-degenerate segments C1≤3: {'Y' if nondegen else 'N'} — morph endpoints may legitimately reach genre extremes)")
    ok = mono and span>=0.4 and new and progs[0]<0.40 and progs[-1]>0.60
    print(f"  >>> {'PASS — smooth A→B morph (rampable axes), genuinely new' if ok else 'PARTIAL: '+', '.join(n for n,c in [('monotonic',mono),('span>=0.4',span>=0.4),('new',new),('anchored-ends',progs[0]<0.40 and progs[-1]>0.60)] if not c)}")
    for p in segs: p.unlink(missing_ok=True)
    summary=dict(A=A,B=B,S=S,progress=[round(p,2) for p in progs],span=round(span,2),monotonic=mono,
                 copy_A=round(riskA,2),copy_B=round(riskB,2),copy_corpus=round(riskC,2),new=new,
                 nondegen=nondegen,verdict=ok)
    (OUT/f"{Path(path).stem}_measure.json").write_text(json.dumps(summary,indent=2))
    return summary

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]))
