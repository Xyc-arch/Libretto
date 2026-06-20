#!/usr/bin/env python3
"""holdout42_setup.py — splits + retrieval (from 314 corpus) for the 42 held-out songs."""
import json, re
from pathlib import Path
import numpy as np
import metric_discovery as md
from understanding_probe import Song

SCRIPT = Path(__file__).resolve().parent
H = SCRIPT / "compositions" / "holdout42"; HG = H / "grammar"
CANON = json.loads((SCRIPT/"corpus_distribution_314.json").read_text())
AXES = CANON["axes_order"]; COLS = {a: np.array(CANON["axes"][a]["values"], float) for a in AXES}
corpus_fp = {s: np.array(v, float) for s, v in
             json.loads((SCRIPT/"compositions"/"continuation"/"corpus_fps.json").read_text()).items()}
man = json.loads((H/"manifest.json").read_text()); K=3

def fp(p):
    m=md.metrics_for(Song(p),p)
    return np.array([round(float((COLS[a]<=float(m[a])).mean()*100)) for a in AXES],float)
def dist(a,b): return float(np.mean(np.abs(a-b)))
def split_blocks(t):
    h,b,cur=[],[],None
    for ln in t.splitlines():
        if ln.startswith("@"):
            if cur is not None:b.append(cur)
            cur=[ln]
        elif cur is None:h.append(ln)
        else:cur.append(ln)
    if cur is not None:b.append(cur)
    return h,b
def write_g(head,groups,path):
    blocks=[x for g in groups for x in g]
    out=[re.sub(r"BARS:\s*\d+",f"BARS: {len(blocks)}",head[0])]+[ln for ln in head[1:] if ln.startswith("VOICES:")]
    for i,blk in enumerate(blocks,1):
        bb=list(blk);bb[0]=re.sub(r"^@\d+",f"@{i}",bb[0]);out.extend(bb)
    Path(path).write_text("\n".join(out)+"\n",encoding="utf-8")
def neighbors(ctx,sid_excl_src):
    cfp=fp(ctx); d=sorted(((dist(cfp,corpus_fp[s]),s) for s in corpus_fp))[:K]   # neighbors from 314 (scaffold)
    return [(s,round(dd,1)) for dd,s in d]

cases={}
for t,items in man["assign"].items():
    for it in items:
        h=it["hsid"]; head,blocks=split_blocks((HG/f"{h}.txt").read_text(encoding="utf-8")); N=len(blocks)
        def R(a,b): return blocks[a:b]
        if t=="cont":
            pre=R(0,round(.75*N)); gap=R(round(.75*N),N); post=None; ctxg=[pre]
        elif t=="infill":
            pre=R(0,round(.40*N)); gap=R(round(.40*N),round(.60*N)); post=R(round(.60*N),N); ctxg=[pre,post]
        else:
            pre=None; gap=R(0,round(.20*N)); post=R(round(.20*N),N); ctxg=[post]
        write_g(head,ctxg,H/f"{h}_{t}_ctx.txt"); write_g(head,[gap],H/f"{h}_{t}_real.txt")
        if pre is not None: write_g(head,[pre],H/f"{h}_{t}_pre.txt")
        if post is not None: write_g(head,[post],H/f"{h}_{t}_post.txt")
        ngh=neighbors(H/f"{h}_{t}_ctx.txt",None)
        cases[f"{h}_{t}"]={"hsid":h,"type":t,"genre":it["genre"],"ctx":f"{h}_{t}_ctx.txt","real":f"{h}_{t}_real.txt",
            "pre":(f"{h}_{t}_pre.txt" if pre is not None else None),"post":(f"{h}_{t}_post.txt" if post is not None else None),
            "target_bars":len(gap),"neighbors":ngh,"hdr":head[0]}
(H/"cases.json").write_text(json.dumps(cases,indent=2))
print(f"{len(cases)} cases. target bars per type (sample):")
for t in ["start","infill","cont"]:
    tb=[cases[c]['target_bars'] for c in cases if cases[c]['type']==t]
    print(f"  {t}: targets {tb}")
print("wrote", H/"cases.json")
