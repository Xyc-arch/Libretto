#!/usr/bin/env python3
"""genre_band_check.py — the self-evolving loop's per-round engine, GENERAL and ADAPTIVE.

Fingerprint a composition against a target band and report what the next round must correct. The
target is genre-ADAPTIVE, not hardcoded to any one genre:

  * The 8 genre-discriminating SPLIT axes (those with genre-conditioned bands) are judged against the
    TARGET GENRE's band [p25,p75], aiming at p50 — out-of-band = EITHER direction (too low = off-genre;
    too high = overshoot/degeneracy). If a genre's [p25,p75] band is degenerate (pinned, e.g. jazz uses
    all 12 pitch-classes so p25=p75=12), it widens to that genre's data-driven [p5,p95] soft band — so
    the rule adapts to the genre's distribution instead of a hand-coded exception.
  * All OTHER axes are judged against the GLOBAL idiomatic band [p25,p75].
  * Degenerate global extremes (<=5 / >=95 pct) are flagged; profile spread is tracked to catch
    mean-collapse; drift vs the previous round is reported. Save the profile to chain rounds.

Pass genre=None to run a pure GLOBAL-band check (genre-agnostic). Works for every corpus genre.

  from libretto.core import genre_band_check as gbc
  gbc.check("piece.txt", genre="jazz", prev="r1.json", save="r2.json")
"""
import json
import sys
from pathlib import Path
import os

import numpy as np

from . import axes_v3 as md                     # v3: 33 discovered axes (md.metrics_for)
from .understanding_probe import Song

SCRIPT = Path(os.environ.get("LIBRETTO_DATA") or (Path(__file__).resolve().parent.parent / "data"))
CANON = json.loads((SCRIPT / "corpus_distribution.json").read_text())
AXES = CANON["axes_order"]
COLS = {a: np.array(CANON["axes"][a]["values"], float) for a in AXES}
GC = CANON["genre_conditioned"]
SPLIT = list(GC.keys())                       # the genre-discriminating axes (data-defined, not hardcoded)


def genres():
    """The genres that have conditioned bands (valid `genre` arguments)."""
    return sorted({g for ax in SPLIT for g in GC[ax]})


def gpct(ax, v):
    return round(float((COLS[ax] <= v).mean() * 100))


def glob_band(ax):
    a = CANON["axes"][ax]
    return a["p25"], a["p50"], a["p75"]


def genre_band(ax, genre):
    """Target genre's band for a split axis, target=p50. Degenerate [p25,p75] widens to [p5,p95]."""
    g = GC[ax][genre]
    lo, hi, p50 = g["p25"], g["p75"], g["p50"]
    axis_range = max(1e-9, CANON["axes"][ax]["p95"] - CANON["axes"][ax]["p5"])
    if (hi - lo) < 0.02 * axis_range:         # pinned band -> use the genre's data-driven soft band
        lo, hi = g["p5"], g["p95"]
    return lo, p50, hi


def check(path, genre=None, prev=None, save=None):
    if genre is not None and genre not in genres():
        raise ValueError(f"unknown genre {genre!r}; valid: {genres()}")
    s = Song(path)
    m = md.metrics_for(s, path)
    nb = len(sorted({e["bar"] for e in s.events}))
    prof = {a: gpct(a, float(m[a])) for a in AXES}
    print(f"FILE {Path(path).name}: {nb} bars | target = {genre or 'GLOBAL band'}")
    oob = []

    if genre is not None:
        print(f"  -- genre-discriminating axes (vs {genre} band [p25,p75]; target=p50) --")
        for ax in SPLIT:
            v = float(m[ax]); lo, p50, hi = genre_band(ax, genre)
            inb = lo <= v <= hi
            st = "in" if inb else ("LOW" if v < lo else "HIGH")
            if not inb:
                oob.append((ax, v, st, round(p50, 3)))
            print(f"     {ax:<24} val={v:<7.3f} {genre}band[{lo:.2f},{hi:.2f}] p50={p50:<5.2f} -> {st}")

    label = "genre-neutral axes" if genre is not None else "all axes"
    print(f"  -- {label} OUT of GLOBAL band (target=global p50) --")
    for ax in AXES:
        if genre is not None and ax in SPLIT:
            continue
        v = float(m[ax]); lo, p50, hi = glob_band(ax)
        if not (lo <= v <= hi):
            d = "LOW" if v < lo else "HIGH"
            oob.append((ax, v, d, round(p50, 3)))
            print(f"     {ax:<24} val={v:<7.3f} globalband[{lo:.2f},{hi:.2f}] -> {d}")

    ext = [a for a in AXES if prof[a] <= 5 or prof[a] >= 95]
    print(f"  degenerate global extremes (<=5/>=95): {len(ext)} -> {[(a.split('_',1)[1], prof[a]) for a in ext]}")
    spread = float(np.std([prof[a] for a in AXES]))
    print(f"  out-of-band total: {len(oob)} | profile spread sd={spread:.1f}")
    if prev:
        pv = json.loads(Path(prev).read_text())
        moved = [(a, pv[a], prof[a]) for a in AXES if abs(prof[a] - pv.get(a, prof[a])) >= 15]
        print("  DRIFT (>=15pct): " + ", ".join(f"{a.split('_',1)[1]} {pv[a]}->{prof[a]}" for a, _, _ in moved))
    if save:
        Path(save).write_text(json.dumps(prof))
        print(f"  saved {save}")
    return oob, ext, nb


if __name__ == "__main__":
    argv = sys.argv[1:]
    save = None
    if "--save" in argv:
        i = argv.index("--save"); save = argv[i + 1]; argv = argv[:i] + argv[i + 2:]
    genre = None
    if "--genre" in argv:
        i = argv.index("--genre"); genre = argv[i + 1]; argv = argv[:i] + argv[i + 2:]
    args = [a for a in argv if not a.startswith("--")]
    prev = args[1] if len(args) > 1 else None
    check(args[0], genre, prev, save)
