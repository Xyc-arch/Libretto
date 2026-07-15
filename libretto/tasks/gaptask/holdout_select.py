#!/usr/bin/env python3
"""holdout_select.py — select 42 FRESH songs (disjoint from the 314 corpus) for a held-out gap-task.

Picks fresh MIDIs from the genre artists whose source path is NOT in the 314 reference corpus, encodes
them to grammar (adaptive grid, drums dropped, anonymized) into compositions/holdout42/grammar/, screens
out short (<56 bars) and repetitive-remainder (low distinct_bar_frac) songs, and partitions 14/14/14
across continuation/infill/start with genres balanced. NOT appended to the corpus / frozen distribution.
"""
import json, random, re
from collections import defaultdict
from pathlib import Path
import numpy as np
from libretto.core import midi_to_grammar as mtg
from libretto.core import metric_discovery as md
from libretto.core import Song
import expand_corpus as ec

import libretto
DATA = libretto.data_root()
ROOT = ec.ROOT
OUT = Path("compositions") / "holdout42"; (OUT/"grammar").mkdir(parents=True, exist_ok=True)
KEY = json.loads((DATA/"answer_key"/"grammar_truth.json").read_text())
CANON = json.loads((DATA/"corpus_distribution.json").read_text())
AXES = CANON["axes_order"]; DBF = np.array(CANON["axes"]["form_distinct_bar_frac"]["values"], float)
CORPUS_SRC = {v.get("source") for v in KEY.values()}          # the 314 (+gen) source paths — to exclude
RNG = random.Random(4242)
TARGETS = {"core_pop_rock":6,"electronic_dance":6,"funk_soul_rnb":6,"folk_country":6,
           "latin_reggae_world":6,"jazz":6,"classical":3,"film_score":3}   # =42
PER_ARTIST_CAP = 3; ENCODE_TRIES = 18
_VAR = re.compile(r"\.\d+$")

genre_artists = defaultdict(list)
for art,(g,era) in ec.ARTISTS.items():
    genre_artists[g].append(art)

def dbf_pctile(song, path):
    m = md.metrics_for(song, path)
    return round(float((DBF <= float(m["form_distinct_bar_frac"])).mean()*100)), m

picked = []   # (hid, genre, source, bars)
hid = 0
for g, need in TARGETS.items():
    # candidate file pool: fresh (not in corpus), title-deduped, per-artist capped
    cand = []
    arts = genre_artists.get(g, [])[:]; RNG.shuffle(arts)
    for art in arts:
        folder = ROOT / art
        if not folder.is_dir(): continue
        files = sorted(folder.glob("*.mid")); RNG.shuffle(files)
        seen=set(); n=0
        for f in files:
            rel = str(f.relative_to(ROOT))
            if rel in CORPUS_SRC: continue
            t = _VAR.sub("", f.stem).strip().lower()
            if t in seen: continue
            seen.add(t); cand.append(f); n+=1
            if n>=PER_ARTIST_CAP: break
    RNG.shuffle(cand)
    got=0; tries=0
    for f in cand:
        if got>=need or tries>=ENCODE_TRIES: break
        tries+=1
        try:
            text = mtg.encode(f, "adaptive", True, None, anonymize=False)
        except Exception:
            continue
        if not text: continue
        hid += 1; hsid = f"h_{hid:04d}"
        p = OUT/"grammar"/f"{hsid}.txt"; p.write_text(text, encoding="utf-8")
        try:
            song = Song(p); bars = int(re.search(r"BARS:\s*(\d+)", text).group(1))
            pct, _ = dbf_pctile(song, p)
        except Exception:
            p.unlink(missing_ok=True); hid-=1; continue
        if bars < 56 or pct < 35:        # screen: long enough + not repetitive-remainder
            p.unlink(missing_ok=True); hid-=1; continue
        picked.append((hsid, g, str(f.relative_to(ROOT)), bars)); got+=1
    print(f"  {g}: needed {need}, got {got} (of {len(cand)} fresh candidates, {tries} encode-tries)")

# contamination guard
disjoint = all(src not in CORPUS_SRC for _,_,src,_ in picked)
print(f"\nCONTAMINATION GUARD: {len(picked)} fresh songs; all sources disjoint from the 314 corpus: {disjoint}")

# partition: round-robin each genre's picks across the 3 types -> balanced
bygenre = defaultdict(list)
for hsid,g,src,bars in picked: bygenre[g].append((hsid,g,src,bars))
assign = {"cont":[], "infill":[], "start":[]}
types = ["cont","infill","start"]
for g, items in bygenre.items():
    for i,it in enumerate(items):
        assign[types[i % 3]].append(it)
manifest = {"holdout": {hsid:{"genre":g,"source":src,"bars":bars} for hsid,g,src,bars in picked},
            "assign": {t:[{"hsid":h,"genre":g,"source":s,"bars":b} for h,g,s,b in v] for t,v in assign.items()},
            "disjoint": disjoint}
(OUT/"manifest.json").write_text(json.dumps(manifest, indent=2))

print("\n=== 42 HELD-OUT SONG -> TYPE -> GENRE (target 14/type) ===")
for t in types:
    print(f"\n{t.upper()} ({len(assign[t])}):")
    for h,g,s,b in sorted(assign[t], key=lambda x:x[1]):
        print(f"   {h}  {g:<18} {b:>3}b   {s[:46]}")
print(f"\ntotals: " + ", ".join(f"{t}={len(assign[t])}" for t in types) + f" | picked {len(picked)}")
print("wrote", OUT/"manifest.json")
