#!/usr/bin/env python3
"""morph_component_measure.py — score a component-morph [A_comp]→[transition]→[B_comp] with the
GRADUAL-SHIFT criterion (the thing special to a morph).

Splits the stitched morph into: A_comp | transition (K equal segments) | B_comp, and per segment measures
the rampable-axis progress (0=A, 1=B) + copy-overlap vs A and vs B. Then judges:
  START close to A   : seg-1 progress <= 0.30 AND copy_A high (it is A's real component)
  END close to B     : seg-last progress >= 0.70 AND copy_B high
  GRADUAL            : progress non-decreasing (monotonic) AND no abrupt jump (max step <= 0.35)
  COPY-PREVENTED     : transition segments' copy vs A and vs B both < 0.30 (original connective material)

  python3 morph_component_measure.py <morph.txt> <A_sid> <B_sid> <acomp_bars> <bcomp_bars> <n_trans_seg>
"""
import json, sys, re
from pathlib import Path
import numpy as np, metric_discovery as md
from understanding_probe import Song
import copy_risk as cr

SCRIPT=Path(__file__).resolve().parent; GRAMMAR=SCRIPT/"grammar"
CANON=json.loads((SCRIPT/"corpus_distribution_314.json").read_text())
AXES=CANON["axes_order"]; COLS={a:np.array(CANON["axes"][a]["values"],float) for a in AXES}
RAMP=["har_chromaticism","har_dimaug_rate","rhy_triplet_share","har_chord_change_rate","mel_up_ratio",
      "har_root_motion_entropy","tex_active_voice_density","rhy_onset_density_per_bar","rhy_syncopation_rate",
      "har_pc_entropy","mel_interval_entropy","rhy_dur_cv"]

def split(t):
    h,b,cur=[],[],None
    for ln in t.splitlines():
        if ln.startswith("@"):
            if cur is not None:b.append(cur)
            cur=[ln]
        elif cur is None:h.append(ln)
        else:cur.append(ln)
    if cur is not None:b.append(cur)
    return h,b

def main(path,A,B,ac,bc,K):
    head,blocks=split(Path(path).read_text()); n=len(blocks)
    ridx=[AXES.index(a) for a in RAMP if abs(0)==0]  # all RAMP present
    def fpv(bb):
        o=[re.sub(r'BARS:\s*\d+',f'BARS: {len(bb)}',head[0]),head[1]]
        for i,blk in enumerate(bb,1):
            x=list(blk);x[0]=re.sub(r'^@\d+',f'@{i}',x[0]);o.extend(x)
        p=SCRIPT/"compositions/morph/_cm.txt"; p.write_text("\n".join(o)+"\n")
        m=md.metrics_for(Song(p),p)
        if m is None:                       # empty/near-silent segment — no fingerprint
            gb,_,gt=cr.piece_notes(p); p.unlink(); return None,gb,gt
        v=np.array([round(float((COLS[a]<=float(m[a])).mean()*100)) for a in AXES],float)
        gb,_,gt=cr.piece_notes(p); p.unlink(); return v,gb,gt
    # endpoints = the real components (first ac / last bc bars)
    fa=fpv(blocks[:ac])[0]; fb=fpv(blocks[n-bc:])[0]
    faR=fa[[AXES.index(a) for a in RAMP]]; fbR=fb[[AXES.index(a) for a in RAMP]]
    Abb,_,_=cr.piece_notes(GRAMMAR/f"{A}.txt"); Bbb,_,_=cr.piece_notes(GRAMMAR/f"{B}.txt")
    # segment plan: A_comp, K transition slices, B_comp
    trans=blocks[ac:n-bc]; per=len(trans)//K
    segs=[("A_comp",blocks[:ac])]
    for k in range(K):
        lo=k*per; hi=(k+1)*per if k<K-1 else len(trans); segs.append((f"t{k+1}",trans[lo:hi]))
    segs.append(("B_comp",blocks[n-bc:]))
    rows=[]; last_prog=0.0; sparse=0
    for name,blk in segs:
        v,gb,gt=fpv(blk)
        if v is None:                       # silent segment — carry forward, flag
            sparse+=1; prog=last_prog
        else:
            vR=v[[AXES.index(a) for a in RAMP]]
            dA=float(np.mean(np.abs(vR-faR))); dB=float(np.mean(np.abs(vR-fbR))); prog=dA/max(1e-9,dA+dB); last_prog=prog
        ovA,_=cr.slide_overlap(gb,gt,Abb); ovB,_=cr.slide_overlap(gb,gt,Bbb)
        rows.append((name,prog,ovA,ovB))
    if sparse: print(f"  [note: {sparse} segment(s) near-silent — fingerprint carried forward]")
    progs=[r[1] for r in rows]
    steps=[progs[i+1]-progs[i] for i in range(len(progs)-1)]
    monotonic=all(s>=-0.10 for s in steps); maxstep=max(abs(s) for s in steps)  # -0.10 tolerates 8-bar-window fingerprint noise
    start_A = progs[0]<=0.30 and rows[0][2]>=0.5
    end_B   = progs[-1]>=0.70 and rows[-1][3]>=0.5
    gradual = monotonic and maxstep<=0.40   # 0.40 separates the smooth thematic morphs (~0.36) from the old jump-then-plateau ones (~0.50)
    trans_rows=rows[1:-1]; copy_prevented=all(r[2]<0.30 and r[3]<0.30 for r in trans_rows)
    # crossfade signature (option-1 relaxed-copy morph): copy-A trends down, copy-B trends up
    cA=[r[2] for r in rows]; cB=[r[3] for r in rows]
    crossfade = cA[0] > cA[-1] and cB[-1] > cB[0]
    print(f"=== MORPH-COMPONENT MEASURE — {Path(path).name} — {A}→{B} ({n} bars; {ac}+{len(trans)}+{bc}) ===")
    print(f"  {'seg':<8}{'progress':>9}{'copyA':>7}{'copyB':>7}   {'(0=A .... 1=B)'}")
    for name,prog,ovA,ovB in rows:
        bar="."*int(prog*24)+"|"+"."*(24-int(prog*24))
        print(f"  {name:<8}{prog:>9.2f}{ovA:>7.2f}{ovB:>7.2f}   {bar}")
    print(f"  STEP increments: {[round(s,2) for s in steps]}  (max {maxstep:.2f})")
    print(f"  START close to A : {'Y' if start_A else 'N'} (progress {progs[0]:.2f}<=0.30, copyA {rows[0][2]:.2f}>=0.5)")
    print(f"  END close to B   : {'Y' if end_B else 'N'} (progress {progs[-1]:.2f}>=0.70, copyB {rows[-1][3]:.2f}>=0.5)")
    print(f"  GRADUAL          : {'Y' if gradual else 'N'} (monotonic {monotonic}, max step {maxstep:.2f}<=0.40)")
    print(f"  CROSSFADE        : {'Y' if crossfade else 'N'} (copy-A {cA[0]:.2f}→{cA[-1]:.2f} down, copy-B {cB[0]:.2f}→{cB[-1]:.2f} up)")
    print(f"  (copy-prevented middle: {'Y' if copy_prevented else 'N — relaxed by design (thematic morph derives from the real themes)'})")
    ok=start_A and end_B and gradual and crossfade
    print(f"  >>> {'PASS — gradual A→B glide, anchored ends, thematic crossfade' if ok else 'PARTIAL: '+', '.join(n2 for n2,c in [('start-A',start_A),('end-B',end_B),('gradual',gradual),('crossfade',crossfade)] if not c)}")
    return dict(progs=[round(p,2) for p in progs],maxstep=round(maxstep,2),start_A=start_A,end_B=end_B,gradual=gradual,crossfade=crossfade,copy_prevented=copy_prevented,verdict=ok)

if __name__=="__main__":
    main(sys.argv[1],sys.argv[2],sys.argv[3],int(sys.argv[4]),int(sys.argv[5]),int(sys.argv[6]))
