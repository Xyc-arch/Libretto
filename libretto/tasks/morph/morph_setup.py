#!/usr/bin/env python3
"""morph_setup.py — prep a fingerprint MORPH between two real pieces A -> B.

A successful morph is a piece whose 28-axis fingerprint TRAJECTORY moves from fp(A) to fp(B): the first
segment sits near A, the last near B, the middle interpolates. The target for segment s (of S) is the
linear blend  target_s = fp(A) + (s/(S-1))*(fp(B)-fp(A)).  Only a coordinate system can define "halfway".

Writes case.json with fp(A), fp(B), the per-segment interpolated targets, the axes that differ most
(the "morph axes" the generator should actively glide), and the key plan. The morph is NEW material that
statistically travels A->B — not a medley of A's and B's actual notes (copy_risk vs A and B must stay low).

Usage: python3 morph_setup.py <A_sid> <B_sid> [segments=6] [seg_bars=9]
"""
import json, sys, re
from pathlib import Path
import numpy as np
import metric_discovery as md
from understanding_probe import Song

SCRIPT = Path(__file__).resolve().parent
GRAMMAR = SCRIPT / "grammar"
OUT = SCRIPT / "compositions" / "morph"; OUT.mkdir(parents=True, exist_ok=True)
KEY = json.loads((SCRIPT/"answer_key"/"grammar_truth.json").read_text())
CANON = json.loads((SCRIPT/"corpus_distribution_314.json").read_text())
AXES = CANON["axes_order"]; COLS = {a: np.array(CANON["axes"][a]["values"], float) for a in AXES}

def fp(p):
    m = md.metrics_for(Song(p), p)
    return {a: round(float((COLS[a] <= float(m[a])).mean()*100)) for a in AXES}
def hdr(sid):
    return (GRAMMAR/f"{sid}.txt").read_text().splitlines()[0]
def keyof(h): return re.search(r"KEY:\s*([^|]+)", h).group(1).strip()
def tempoof(h): return int(re.search(r"TEMPO:\s*(\d+)", h).group(1))

def main(A, B, S=6, seg_bars=9):
    fa, fb = fp(GRAMMAR/f"{A}.txt"), fp(GRAMMAR/f"{B}.txt")
    ha, hb = hdr(A), hdr(B)
    targets = []   # per segment: interpolated percentile target for every axis
    for s in range(S):
        frac = s/(S-1)
        targets.append({a: round(fa[a] + frac*(fb[a]-fa[a])) for a in AXES})
    # morph axes = where A and B differ most (these must actively glide)
    morph_axes = sorted(AXES, key=lambda a: abs(fa[a]-fb[a]), reverse=True)[:10]
    case = dict(A=A, B=B, S=S, seg_bars=seg_bars, total_bars=S*seg_bars,
                fpA=fa, fpB=fb, targets=targets, morph_axes=morph_axes,
                keyA=keyof(ha), keyB=keyof(hb), tempoA=tempoof(ha), tempoB=tempoof(hb),
                genreA=KEY[A].get("genre","orig"), genreB=KEY[B].get("genre","orig"),
                titleA=KEY[A].get("title"), titleB=KEY[B].get("title"))
    (OUT/f"morph_{A}_{B}_case.json").write_text(json.dumps(case,indent=2))
    print(f"=== MORPH SETUP — {A} ({case['genreA']}, {case['titleA']}) -> {B} ({case['genreB']}, {case['titleB']}) ===")
    print(f"  {S} segments x {seg_bars} bars = {S*seg_bars} bars | key {case['keyA']} -> {case['keyB']} | tempo {case['tempoA']} -> {case['tempoB']}")
    print(f"\n  TOP MORPH AXES (A%→B%) — these must glide across the piece:")
    for a in morph_axes:
        print(f"     {a.split('_',1)[1]:<24} {fa[a]:>3} -> {fb[a]:>3}")
    print(f"\n  per-segment targets on the morph axes (segment 1 ≈ A ... segment {S} ≈ B):")
    for s in range(S):
        vals = ", ".join(f"{a.split('_',1)[1]}={targets[s][a]}" for a in morph_axes[:5])
        print(f"     seg{s+1}: {vals}")
    print(f"\n  wrote {OUT/f'morph_{A}_{B}_case.json'}")

if __name__ == "__main__":
    A, B = sys.argv[1], sys.argv[2]
    S = int(sys.argv[3]) if len(sys.argv)>3 else 6
    sb = int(sys.argv[4]) if len(sys.argv)>4 else 9
    main(A, B, S, sb)
