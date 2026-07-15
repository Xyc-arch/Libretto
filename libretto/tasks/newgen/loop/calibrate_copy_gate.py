#!/usr/bin/env python3
"""calibrate_copy_gate.py — set the novelty gate from the REAL corpus, genre-conditioned.

copy_risk(piece) = max note-overlap with the nearest corpus song. To know what overlap is NORMAL for a
genre, we measure each real song's overlap with its nearest OTHER corpus song (leave-one-out) and take the
per-genre distribution. Writes `genre_copy_budget` {genre: {p90, median, n}} into corpus_distribution.json.

NOTE: p90 is inflated by clean_midi's near-DUPLICATE songs (hits 0.9+ for dup-heavy genres); feedback.py
caps the gate at COPY_CAP=0.55 (the recognizable-variation line) so it never permits a near-copy. Re-run
this after a corpus/distribution rebuild (it's O(N^2), a few minutes — not folded into distribution.py).

  python newgen_loop/calibrate_copy_gate.py [--sample 40]
"""
import argparse
import importlib
import json
import random
import sys
from pathlib import Path

import numpy as np

PROJ = Path(__file__).resolve().parents[4]     # repo root
sys.path.insert(0, str(PROJ))
importlib.import_module("libretto.core.copy_risk")
CR = sys.modules["libretto.core.copy_risk"]              # real module (bypasses the package __init__ shadow)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=40, help="songs per genre to estimate p90 (0 = all)")
    a = ap.parse_args()
    truth = json.loads((PROJ / "libretto/data/answer_key/grammar_truth.json").read_text())
    corp = CR.load_corpus()
    bg = {}
    for s in corp:
        g = truth.get(s, {}).get("genre")
        if g:
            bg.setdefault(g, []).append(s)

    def loo_max(sid):
        bb, bag, total = corp[sid]
        pre = sorted(((len(bag & corp[o][1]) / max(1, len(bag)), o) for o in corp if o != sid),
                     reverse=True)[:CR.PREFILTER_TOPK]
        return max((CR.slide_overlap(bb, total, corp[o][0])[0] for _, o in pre), default=0.0)

    random.seed(7)
    budget = {}
    print(f"{'genre':16} {'n':>4} {'median':>7} {'p90':>5}  (real-song nearest-neighbor overlap)")
    for g in sorted(bg):
        pool = bg[g]
        samp = pool if a.sample <= 0 else random.sample(pool, min(a.sample, len(pool)))
        vals = np.array([loo_max(s) for s in samp])
        budget[g] = {"p90": round(float(np.percentile(vals, 90)), 2),
                     "median": round(float(np.median(vals)), 2), "n": len(samp)}
        print(f"{g:16} {len(samp):>4} {np.median(vals):>7.2f} {np.percentile(vals, 90):>5.2f}")
    distp = PROJ / "libretto/data/corpus_distribution.json"
    dist = json.loads(distp.read_text())
    dist["genre_copy_budget"] = budget
    distp.write_text(json.dumps(dist))
    print("\nstored genre_copy_budget in corpus_distribution.json (feedback.py caps the gate at 0.55)")


if __name__ == "__main__":
    main()
