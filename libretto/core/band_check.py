#!/usr/bin/env python3
"""
band_check.py — fingerprint a composition and judge it against the idiomatic BAND, not the mean.

Fitness target = the corpus DISTRIBUTION: each axis should land in the idiomatic band (25th–75th
percentile) and NOT at an extreme (<5th / >95th). In-band axes need NO correction; only out-of-band
axes drive KB refinement. The loop REDUCES ATYPICALITY — it does NOT chase the mean (that would
collapse variance into the bland statistical center = mediocrity).

Usage: python3 band_check.py <grammar.txt> [prev_profile.json] [--save out.json]
Prints per-axis percentile + band status, the out-of-band/extreme lists, profile spread (sd of
percentiles), mean-proximity, and — if a previous profile is given — per-axis drift classified
toward-band / away / centering, plus a mediocrity-trap check (variance collapse).
"""
import json
import sys
import os
from pathlib import Path

import numpy as np

from . import metric_discovery as md
from .understanding_probe import Song

SCRIPT = Path(os.environ.get("LIBRETTO_DATA") or (Path(__file__).resolve().parent.parent / "data"))
CANON = json.loads((SCRIPT / "corpus_distribution_314.json").read_text())   # FROZEN canonical reference
AXES = CANON["axes_order"]
CORPUS = {m: CANON["axes"][m]["values"] for m in AXES}
LO_EXT, LO, HI, HI_EXT = 5, 25, 75, 95


def status(p):
    if p < LO_EXT: return "EXT-LO"
    if p < LO:     return "lo"
    if p <= HI:    return "in"
    if p <= HI_EXT:return "hi"
    return "EXT-HI"


def profile(path):
    m = md.metrics_for(Song(path), path)
    out = {}
    for a in AXES:
        col = np.array(CORPUS[a], float)
        out[a] = round(float((col <= float(m[a])).mean() * 100))
    return out


def main():
    argv = sys.argv[1:]
    save = None
    if "--save" in argv:
        i = argv.index("--save")
        save = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    args = [a for a in argv if not a.startswith("--")]
    path = args[0]
    prev = json.loads(Path(args[1]).read_text()) if len(args) > 1 else None

    prof = profile(path)
    pcts = np.array([prof[a] for a in AXES])
    spread = float(pcts.std())
    mean_prox = float(np.mean(np.abs(pcts - 50)))       # high = far from center (good if in-band)
    near_mean = sum(1 for p in pcts if 40 <= p <= 60)
    oob = [(a, prof[a], status(prof[a])) for a in AXES if status(prof[a]) != "in"]
    ext = [(a, prof[a], status(prof[a])) for a in AXES if status(prof[a]) in ("EXT-LO", "EXT-HI")]

    print(f"FILE: {Path(path).name}")
    print(f"  in-band(25-75): {len(AXES)-len(oob)}/{len(AXES)} | out-of-band: {len(oob)} | EXTREME(<5/>95): {len(ext)}")
    print(f"  profile spread (sd of %iles): {spread:.1f}   mean-proximity (avg|p-50|): {mean_prox:.1f}"
          f"   near-mean[40-60]: {near_mean}/28")
    if ext:
        print("  EXTREME axes: " + ", ".join(f"{a.split('_',1)[1]} {p}%({s})" for a, p, s in ext))
    print("  out-of-band axes:")
    for a, p, s in sorted(oob, key=lambda t: abs(t[1] - 50), reverse=True):
        print(f"     {a:<26} {p:>3}%  {s}")

    if prev:
        print("\n  DRIFT vs previous round:")
        moved = []
        for a in AXES:
            d = prof[a] - prev.get(a, prof[a])
            if d != 0:
                moved.append((a, prev[a], prof[a], d))
        # classify
        toward = away = center = 0
        for a, p0, p1, d in sorted(moved, key=lambda t: -abs(t[3])):
            s0, s1 = status(p0), status(p1)
            # toward-band: an out-of-band axis moving into [25,75]
            if s0 != "in":
                tb = (d > 0 and p0 < LO) or (d < 0 and p0 > HI)
                kind = "toward-band" if tb else "AWAY"
            else:
                # in-band: moving toward 50 from an edge = centering (watch); else 'in-band shuffle'
                kind = "centering" if abs(p1 - 50) < abs(p0 - 50) - 3 else "in-band"
            if kind == "toward-band": toward += 1
            elif kind == "AWAY": away += 1
            elif kind == "centering": center += 1
            print(f"     {a:<26} {p0:>3}% -> {p1:>3}%  ({d:+d}, {kind})")
        # mediocrity-trap check
        prev_spread = float(np.std([prev[a] for a in AXES if a in prev]))
        prev_nearmean = sum(1 for a in AXES if a in prev and 40 <= prev[a] <= 60)
        print(f"\n  mediocrity-trap watch: spread {prev_spread:.1f} -> {spread:.1f}"
              f" ({'COLLAPSING (bad)' if spread < prev_spread - 3 else 'retained'}); "
              f"near-mean {prev_nearmean} -> {near_mean}; toward-band {toward}, away {away}, centering {center}")
        verdict = ("HEALTHY: extremes/out-of-band reduced, spread retained"
                   if spread >= prev_spread - 3 and toward >= away else
                   "WATCH: possible mean-collapse or axes moving away from band")
        print(f"  -> {verdict}")

    if save:
        Path(save).write_text(json.dumps(prof, indent=2))
        print(f"\n  saved profile -> {save}")
    return prof


if __name__ == "__main__":
    main()
