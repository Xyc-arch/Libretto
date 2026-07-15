#!/usr/bin/env python3
"""within_song_variation.py — a candidate 29th axis: how much a song's LOCAL musical character drifts
across its span.

WSV(song) = split the song into W equal windows; compute each window's metric vector over the
RHYTHM/HARMONY/MELODY/TEXTURE axes (the local-character axes); normalize each axis by its corpus SD;
WSV = mean over those axes of (std across windows). High = the song changes a lot internally
(sparse↔dense, simple↔complex sections); low = homogeneous throughout.

Deliberately EXCLUDES the 4 FORM axes (self_similarity, novelty_rate, distinct_bar_frac,
section_per100bars) — those already measure bar-pattern repetition; WSV measures local-character drift,
a distinct dimension (kept distinct to satisfy decorrelation |r|<0.75).
"""
import json, re
import os
from pathlib import Path
import numpy as np
from . import metric_discovery as md
from .understanding_probe import Song

SCRIPT = Path(os.environ.get("LIBRETTO_DATA") or (Path(__file__).resolve().parent.parent / "data"))
CANON = json.loads((SCRIPT/"corpus_distribution.json").read_text())
AXES = CANON["axes_order"]
FORM = {"form_self_similarity","form_novelty_rate","form_distinct_bar_frac","form_section_per100bars"}
# 24 local-character axes: exclude the FORM axes (already measure repetition) AND the axis itself
WSV_AXES = [a for a in AXES if a not in FORM and a != "within_song_variation"]
SD = {a: (CANON["axes"][a]["sd"] or 1e-9) for a in WSV_AXES}
WINDOWS = 6

def _split_blocks(text):
    head, blocks, cur = [], [], None
    for ln in text.splitlines():
        if ln.startswith("@"):
            if cur is not None: blocks.append(cur)
            cur=[ln]
        elif cur is None: head.append(ln)
        else: cur.append(ln)
    if cur is not None: blocks.append(cur)
    return head, blocks

def wsv(path, tmp=None):
    head, blocks = _split_blocks(Path(path).read_text())
    n = len(blocks)
    W = min(WINDOWS, max(2, n//6))
    if W < 2 or n < 4: return None
    per = n//W
    tmp = Path(tmp or (SCRIPT/"_wsv_tmp.txt"))
    vecs = []
    for w in range(W):
        lo=w*per; hi=(w+1)*per if w<W-1 else n
        bb=blocks[lo:hi]
        out=[re.sub(r"BARS:\s*\d+",f"BARS: {len(bb)}",head[0])]+[l for l in head[1:] if l.startswith("VOICES:")]
        for i,blk in enumerate(bb,1):
            x=list(blk); x[0]=re.sub(r"^@\d+",f"@{i}",x[0]); out.extend(x)
        tmp.write_text("\n".join(out)+"\n")
        m = md.metrics_for(Song(tmp), tmp, base_only=True)   # base_only avoids recursion
        vecs.append([float(m[a]) for a in WSV_AXES])
    tmp.unlink(missing_ok=True)
    V = np.array(vecs, float)                                  # (W, 24)
    std_per_axis = V.std(axis=0)                               # std across windows
    norm = std_per_axis / np.array([SD[a] for a in WSV_AXES])  # in corpus-SD units
    return float(np.mean(norm))

if __name__ == "__main__":
    import sys
    print(f"WSV({sys.argv[1]}) = {wsv(sys.argv[1]):.3f}")
