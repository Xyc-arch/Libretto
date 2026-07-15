#!/usr/bin/env python3
"""gaptask21_measure.py — measure + genre-aware gate the 21 runs; per-type pass-rate + proximity compare."""
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
GRAMMAR = DATA / "grammar"; GT = Path("compositions") / "gaptask21"
KEY = json.loads((DATA/"answer_key"/"grammar_truth.json").read_text())
CANON = json.loads((DATA/"corpus_distribution.json").read_text())
AXES = CANON["axes_order"]; COLS = {a: np.array(CANON["axes"][a]["values"], float) for a in AXES}
GC = CANON["genre_conditioned"]
corpus_fp = {s: np.array(v, float) for s, v in
             json.loads((DATA / "corpus_fps.json").read_text()).items()}
cases = json.loads((GT/"cases.json").read_text())

def fp(p):
    m=md.metrics_for(Song(p),p)
    return np.array([round(float((COLS[a]<=float(m[a])).mean()*100)) for a in AXES],float)
def dist(a,b): return float(np.mean(np.abs(a-b)))
def ga_extremes(p, genre):     # genre-aware C1 (#1): exempt split-axis global-extreme if within genre band
    m=md.metrics_for(Song(p),p); out=[]
    for a in AXES:
        v=float(m[a]); pct=float((COLS[a]<=v).mean()*100)
        if pct<=5 or pct>=95:
            if a in GC and genre in GC[a] and GC[a][genre]["p25"]<=v<=GC[a][genre]["p75"]: continue
            out.append(a.split('_',1)[1])
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
    gen=GT/f"{cid}_gen.txt"
    cfp=fp(GT/c["ctx"]); gfp=fp(gen); rfp=fp(GT/c["real"])
    D_cg=dist(cfp,gfp); D_gr=dist(gfp,rfp)
    rand=sorted(dist(rfp,corpus_fp[s]) for s in corpus_fp if s!=c["sid"])
    beat=round(sum(1 for d in rand if d>D_gr)/len(rand)*100)
    ge=ga_extremes(gen,c["genre"])
    gb=barsigs(gen); n=max(1,len(gb)); realb=set(barsigs(GT/c["real"])); neighb=set()
    for nsid,_ in c["neighbors"]:
        for sg in barsigs(GRAMMAR/f"{nsid}.txt"): neighb.add(sg)
    cpr=round(sum(1 for b in gb if b in realb)/n*100); cpn=round(sum(1 for b in gb if b in neighb)/n*100)
    h8=harm8(gen); cp8=round(sum(1 for g in h8 if g in CH8)/max(1,len(h8))*100) if h8 else 0
    gbars=len(sorted({e["bar"] for e in Song(gen).events})); rbars=len(sorted({e["bar"] for e in Song(GT/c["real"]).events}))
    c1=len(ge)<=region_c1_budget(c["genre"]); c2=abs(gbars-rbars)<=2; c3=(cpr<5 and cpn<5 and cp8<10); repl=cpr>=20 or (D_gr<5 and cp8>=20)
    rows[cid]=dict(t=c["type"],sid=c["sid"],g=c["genre"],D_gr=round(D_gr,1),D_cg=round(D_cg,1),beat=beat,
        gext=len(ge),c1=c1,c2=c2,c3=c3,cpr=cpr,cpn=cpn,cp8=cp8,repl=repl)

print("="*118)
print(f"{'song':<11}{'type':<6}{'genre':<14}{'D_gr':>5}{'D_cg':>5}{'beat%':>6}{'gaC1':>5}{'C1':>3}{'C2':>3}{'C3':>3}{'cpR':>5}{'cpN':>4}{'8g':>4}{'PASS':>6}")
print("-"*118)
for t in ["start","infill","cont"]:
    for cid in [c for c in cases if rows[c]['t']==t]:
        r=rows[cid]; p=r['c1'] and r['c2'] and r['c3'] and not r['repl']
        print(f"{r['sid']:<11}{t:<6}{r['g'][:13]:<14}{r['D_gr']:>5}{r['D_cg']:>5}{r['beat']:>5}%{r['gext']:>5}"
              f"{'Y' if r['c1'] else 'N':>3}{'Y' if r['c2'] else 'N':>3}{'Y' if r['c3'] else 'N':>3}{r['cpr']:>4}%{r['cpn']:>3}%{r['cp8']:>3}%{'PASS' if p else '':>6}")

print("\n=== GATE-PASS RATE PER TYPE (n=7 each) ===")
for t in ["start","infill","cont"]:
    cc=[rows[c] for c in cases if rows[c]['t']==t]
    npass=sum(1 for r in cc if r['c1'] and r['c2'] and r['c3'] and not r['repl'])
    print(f"  {t:<6}: {npass}/7 pass all genre-aware gates")

print("\n=== PROXIMITY ACROSS TYPES (do starts land farther from their real region?) ===")
for t in ["start","infill","cont"]:
    cc=[rows[c] for c in cases if rows[c]['t']==t]
    dgr=[r['D_gr'] for r in cc]; bt=[r['beat'] for r in cc]
    print(f"  {t:<6}: D_gr mean={np.mean(dgr):.1f} median={np.median(dgr):.1f} | beat% mean={np.mean(bt):.0f} | D_cg mean={np.mean([r['D_cg'] for r in cc]):.1f}")

print("\n=== BEST gate-passer per type (PASS all + not repl; highest beat%, then lowest D_cg) ===")
winners={}
for t in ["start","infill","cont"]:
    cc=[(c,rows[c]) for c in cases if rows[c]['t']==t and rows[c]['c1'] and rows[c]['c2'] and rows[c]['c3'] and not rows[c]['repl']]
    rank=sorted(cc,key=lambda x:(-x[1]['beat'],x[1]['D_cg']))
    if rank:
        winners[t]=rank[0][0]
        print(f"  {t:<6}: WINNER {rank[0][0]} (beat {rank[0][1]['beat']}%, D_cg {rank[0][1]['D_cg']}, D_gr {rank[0][1]['D_gr']})  | runners: {[c for c,_ in rank[1:3]]}")
    else:
        print(f"  {t:<6}: NO clean gate-passer — none rendered.")
(GT/"winners.json").write_text(json.dumps(winners))
(GT/"measure.json").write_text(json.dumps(rows,indent=2))
