#!/usr/bin/env python3
"""gaptask21_setup.py — 21 distinct songs partitioned 7/type (start/infill/continuation), genre-balanced."""
import json, re
from pathlib import Path
import numpy as np
import metric_discovery as md
from understanding_probe import Song

SCRIPT = Path(__file__).resolve().parent
GRAMMAR = SCRIPT / "grammar"
OUT = SCRIPT / "compositions" / "gaptask21"; OUT.mkdir(parents=True, exist_ok=True)
KEY = json.loads((SCRIPT/"answer_key"/"grammar_truth.json").read_text())
CANON = json.loads((SCRIPT/"corpus_distribution_314.json").read_text())
AXES = CANON["axes_order"]; COLS = {a: np.array(CANON["axes"][a]["values"], float) for a in AXES}
corpus_fp = {s: np.array(v, float) for s, v in
             json.loads((SCRIPT/"compositions"/"continuation"/"corpus_fps.json").read_text()).items()}
K = 3
# each type: 2 hard chromatic-rich genres (jazz/classical/film) + 5 easy — balanced across types
ASSIGN = {
 "start":  ["song_0132","song_0280","song_0002","song_0066","song_0265","song_0202","song_0298"],  # jazz,film,pop,core,folk,elec,latin
 "infill": ["song_0134","song_0169","song_0004","song_0071","song_0261","song_0211","song_0225"],  # jazz,classical,pop,core,folk,elec,funk
 "cont":   ["song_0165","song_0279","song_0011","song_0072","song_0264","song_0224","song_0295"],  # classical,film,pop,core,folk,funk,latin
}

def fp(p):
    m = md.metrics_for(Song(p), p)
    return np.array([round(float((COLS[a] <= float(m[a])).mean()*100)) for a in AXES], float)
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
def write_g(head, groups, path):
    blocks=[x for g in groups for x in g]
    out=[re.sub(r"BARS:\s*\d+", f"BARS: {len(blocks)}", head[0])]
    out+=[ln for ln in head[1:] if ln.startswith("VOICES:")]
    for i,blk in enumerate(blocks,1):
        bb=list(blk); bb[0]=re.sub(r"^@\d+", f"@{i}", bb[0]); out.extend(bb)
    Path(path).write_text("\n".join(out)+"\n", encoding="utf-8")
def neighbors(ctx_path, sid):
    cfp=fp(ctx_path); d=sorted(((dist(cfp,corpus_fp[s]),s) for s in corpus_fp if s!=sid))[:K]
    cen=np.mean([corpus_fp[s] for _,s in d],axis=0)
    sal=sorted(range(len(AXES)),key=lambda i:abs(cen[i]-50),reverse=True)[:6]
    return [(s,round(dd,1)) for dd,s in d], ", ".join(f"{AXES[i].split('_',1)[1]}={int(cen[i])}" for i in sal)

cases={}
for t,sids in ASSIGN.items():
    for sid in sids:
        head,blocks=split_blocks((GRAMMAR/f"{sid}.txt").read_text(encoding="utf-8")); N=len(blocks)
        def R(a,b): return blocks[a:b]
        if t=="cont":
            pre=R(0,round(.75*N)); gap=R(round(.75*N),N); post=None; ctxg=[pre]
        elif t=="infill":
            pre=R(0,round(.40*N)); gap=R(round(.40*N),round(.60*N)); post=R(round(.60*N),N); ctxg=[pre,post]
        else: # start: context = later 80% ONLY, hold out first 20%
            pre=None; gap=R(0,round(.20*N)); post=R(round(.20*N),N); ctxg=[post]
        write_g(head, ctxg, OUT/f"{sid}_{t}_ctx.txt")
        write_g(head, [gap], OUT/f"{sid}_{t}_real.txt")
        if pre is not None: write_g(head,[pre], OUT/f"{sid}_{t}_pre.txt")
        if post is not None: write_g(head,[post], OUT/f"{sid}_{t}_post.txt")
        ngh,tend=neighbors(OUT/f"{sid}_{t}_ctx.txt", sid)
        cases[f"{sid}_{t}"]={"sid":sid,"type":t,"ctx":f"{sid}_{t}_ctx.txt","real":f"{sid}_{t}_real.txt",
            "pre":(f"{sid}_{t}_pre.txt" if pre is not None else None),
            "post":(f"{sid}_{t}_post.txt" if post is not None else None),
            "target_bars":len(gap),"neighbors":ngh,"tend":tend,
            "genre":KEY[sid].get('genre') or 'pop_rock_orig',"hdr":head[0]}
(OUT/"cases.json").write_text(json.dumps(cases,indent=2))

print("21 SONG -> TYPE -> GENRE assignment (7 per type, genres balanced):")
for t in ["start","infill","cont"]:
    print(f"\n  {t.upper()}:")
    for sid in ASSIGN[t]:
        c=cases[f"{sid}_{t}"]
        print(f"    {sid}  {c['genre']:<16} {KEY[sid]['artist'][:20]:<20} — {KEY[sid]['title'][:24]:<24} tgt {c['target_bars']}b  nn={[n for n,_ in c['neighbors']]}")
allsids=[s for v in ASSIGN.values() for s in v]
print(f"\n{len(allsids)} songs, {len(set(allsids))} distinct (no repeat: {len(set(allsids))==len(allsids)})")
print("wrote", OUT/"cases.json")
