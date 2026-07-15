#!/usr/bin/env python3
"""holdout42_measure.py — measure + genre-aware gate the 42 held-out runs; per-type pass-rate + proximity."""
import json
from collections import defaultdict
from pathlib import Path
import numpy as np
from libretto.core import pattern_catalog as pc
from libretto.core import metric_discovery as md
from libretto.core import Song
from libretto.tasks.gaptask.refine_loop import region_c1_budget

import libretto
DATA = libretto.data_root()
GRAMMAR = DATA / "grammar"; H = Path("compositions") / "holdout42"
CANON = json.loads((DATA/"corpus_distribution.json").read_text())
AXES = CANON["axes_order"]; COLS = {a: np.array(CANON["axes"][a]["values"], float) for a in AXES}
GC = CANON["genre_conditioned"]
corpus_fp = {s: np.array(v, float) for s, v in
             json.loads((DATA / "corpus_fps.json").read_text()).items()}
cases = json.loads((H/"cases.json").read_text())

def fp(p):
    m=md.metrics_for(Song(p),p)
    return np.array([round(float((COLS[a]<=float(m[a])).mean()*100)) for a in AXES],float)
def dist(a,b): return float(np.mean(np.abs(a-b)))
def ga_ext(p,genre):
    m=md.metrics_for(Song(p),p); out=[]
    for a in AXES:
        v=float(m[a]); pct=float((COLS[a]<=v).mean()*100)
        if pct<=5 or pct>=95:
            if a in GC and genre in GC[a] and GC[a][genre]["p25"]<=v<=GC[a][genre]["p75"]: continue
            out.append(a)
    return out
def barsigs(p):
    s=Song(p); out=[]
    for b in sorted({e["bar"] for e in s.events}):
        sg=frozenset((round(e["onb"],2),e["midi"]) for e in s.events if e["bar"]==b)
        if len(sg)>=3: out.append(sg)
    return out
def harm8(p):
    s=Song(p); seq=[]
    for b in sorted({e["bar"] for e in s.events}):
        w=defaultdict(float)
        for e in s.events:
            if e["bar"]==b: w[e["pc"]]+=e["dur"]
        seq.append(frozenset(pc.prominent_pcs(w)))
    return [tuple(seq[i:i+8]) for i in range(len(seq)-7)]

CORP=set(); CH8=set()
for f in sorted(GRAMMAR.glob("song_*.txt")):
    if f.stem=="song_0014": continue
    for sg in barsigs(f): CORP.add(sg)
    for g in harm8(f): CH8.add(g)

rows={}
for cid,c in cases.items():
    gen=H/f"{cid}_gen.txt"
    if not gen.exists(): print("MISSING",cid); continue
    cfp=fp(H/c["ctx"]); gfp=fp(gen); rfp=fp(H/c["real"])
    D_cg=dist(cfp,gfp); D_gr=dist(gfp,rfp)
    rand=sorted(dist(rfp,corpus_fp[s]) for s in corpus_fp)
    beat=round(sum(1 for d in rand if d>D_gr)/len(rand)*100)
    ge=ga_ext(gen,c["genre"]); gb=barsigs(gen); n=max(1,len(gb))
    realb=set(barsigs(H/c["real"])); neighb=set()
    for nsid,_ in c["neighbors"]:
        for sg in barsigs(GRAMMAR/f"{nsid}.txt"): neighb.add(sg)
    cpr=round(sum(1 for b in gb if b in realb)/n*100); cpn=round(sum(1 for b in gb if b in neighb)/n*100)
    h8=harm8(gen); cp8=round(sum(1 for g in h8 if g in CH8)/max(1,len(h8))*100) if h8 else 0
    gbars=len(sorted({e["bar"] for e in Song(gen).events})); rbars=len(sorted({e["bar"] for e in Song(H/c["real"]).events}))
    c1=len(ge)<=region_c1_budget(c["genre"]); c2=abs(gbars-rbars)<=2; c3=(cpr<5 and cpn<5 and cp8<10); repl=cpr>=20 or (D_gr<5 and cp8>=20)
    rows[cid]=dict(h=c["hsid"],t=c["type"],g=c["genre"],D_gr=round(D_gr,1),D_cg=round(D_cg,1),beat=beat,
        gext=len(ge),c1=c1,c2=c2,c3=c3,cpr=cpr,cpn=cpn,cp8=cp8,repl=repl)

print("="*116)
print(f"{'song':<8}{'type':<7}{'genre':<14}{'D_gr':>5}{'D_cg':>5}{'beat%':>6}{'gaC1':>5}{'C1':>3}{'C2':>3}{'C3':>3}{'cpR':>5}{'cpN':>4}{'8g':>4}{'PASS':>6}")
print("-"*116)
for t in ["start","infill","cont"]:
    for cid in [c for c in cases if rows.get(c,{}).get('t')==t]:
        r=rows[cid]; p=r['c1'] and r['c2'] and r['c3'] and not r['repl']
        print(f"{r['h']:<8}{t:<7}{r['g'][:13]:<14}{r['D_gr']:>5}{r['D_cg']:>5}{r['beat']:>5}%{r['gext']:>5}"
              f"{'Y' if r['c1'] else 'N':>3}{'Y' if r['c2'] else 'N':>3}{'Y' if r['c3'] else 'N':>3}{r['cpr']:>4}%{r['cpn']:>3}%{r['cp8']:>3}%{'PASS' if p else '':>6}")

print("\n=== GATE-PASS RATE PER TYPE (n=14) ===")
for t in ["start","infill","cont"]:
    cc=[rows[c] for c in cases if rows[c]['t']==t]
    npass=sum(1 for r in cc if r['c1'] and r['c2'] and r['c3'] and not r['repl'])
    print(f"  {t:<6}: {npass}/14 pass all genre-aware gates")
print("\n=== PROXIMITY BY TYPE (out-of-sample) ===")
for t in ["start","infill","cont"]:
    cc=[rows[c] for c in cases if rows[c]['t']==t]
    print(f"  {t:<6}: D_gr mean={np.mean([r['D_gr'] for r in cc]):.1f} median={np.median([r['D_gr'] for r in cc]):.1f} | "
          f"beat% mean={np.mean([r['beat'] for r in cc]):.0f} | D_cg mean={np.mean([r['D_cg'] for r in cc]):.1f}")
(H/"measure.json").write_text(json.dumps(rows,indent=2))
print("\nwrote", H/"measure.json")
