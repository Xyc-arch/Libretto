#!/usr/bin/env python3
"""
fingerprint.py — print any song's percentile profile against the frozen canonical distribution.

Locates a song in the descriptive coordinate system discovered by metric_discovery.py: for each RETAINED
axis (read dynamically from corpus_distribution_314.json — currently 29: the 28 validated axes + the
within_song_variation axis added 2026-06-13) it computes the song's value and its PERCENTILE within the
314 real corpus songs. DESCRIPTIVE only — a percentile is typicality/position, not quality.

Works on any grammar file, so you can fingerprint a freshly COMPOSED piece against the
corpus (e.g. for the KB A/B test: does the KB-assisted composition fingerprint closer to
real music than the no-KB one?).

Usage:
    python3 fingerprint.py song_0047                  # a corpus song by id
    python3 fingerprint.py grammar/song_0047.txt      # by path
    python3 fingerprint.py /path/to/my_composition.txt
    python3 fingerprint.py song_0047 --json           # machine-readable profile

Requires metric_corpus.json (written by metric_discovery.py). Run that once first.
"""
import json
import sys
import os
from pathlib import Path

import numpy as np

from .metric_discovery import metrics_for          # the deterministic metric computations
from .understanding_probe import Song

SCRIPT_DIR = Path(os.environ.get("LIBRETTO_DATA") or (Path(__file__).resolve().parent.parent / "data"))
CANON = SCRIPT_DIR / "corpus_distribution_314.json"   # FROZEN canonical reference (build_canonical_distribution.py)
GRAMMAR_DIR = SCRIPT_DIR / "grammar"
ANSWER_KEY = SCRIPT_DIR / "answer_key" / "grammar_truth.json"
CAT_NAMES = {"rhy": "RHYTHM", "har": "HARMONY", "mel": "MELODY", "tex": "TEXTURE", "form": "FORM"}


def resolve(arg):
    p = Path(arg)
    if p.exists():
        return p
    cand = GRAMMAR_DIR / (arg if arg.endswith(".txt") else arg + ".txt")
    if cand.exists():
        return cand
    raise SystemExit(f"Not found: {arg} (tried {p} and {cand})")


def bar(pct, width=20):
    fill = round(pct / 100 * width)
    return "[" + "#" * fill + "-" * (width - fill) + "]"


def profile(path):
    if not CANON.exists():
        raise SystemExit(f"Missing {CANON.name}. Run:  python3 build_canonical_distribution.py")
    doc = json.loads(CANON.read_text(encoding="utf-8"))
    metrics, axes, n = doc["axes_order"], doc["axes"], doc["header"]["n_songs"]
    vals = metrics_for(Song(path), path)
    if vals is None:
        raise SystemExit(f"No pitched content in {path}")
    out = {}
    for m in metrics:
        v = float(vals[m])
        col = np.array(axes[m]["values"], float)              # frozen empirical distribution
        pct = round(float((col <= v).mean() * 100))           # identical scoring rule as before
        out[m] = {"value": round(v, 4), "percentile": pct,
                  "corpus_mean": axes[m]["mean"],
                  "corpus_range": [axes[m]["min"], axes[m]["max"]]}
    return out, n


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    as_json = "--json" in sys.argv
    if not args:
        raise SystemExit(__doc__)
    path = resolve(args[0])
    prof, n = profile(path)

    if as_json:
        print(json.dumps({"source": str(path), "n_corpus": n, "profile": prof}, indent=2))
        return

    # label if it's a corpus song
    sid = path.stem
    label = ""
    if ANSWER_KEY.exists():
        t = json.loads(ANSWER_KEY.read_text(encoding="utf-8")).get(sid, {})
        if t:
            label = f"  ({t.get('artist','?')} — {t.get('title','?')})"
    print("=" * 78)
    print(f"FINGERPRINT: {sid}{label}")
    print(f"percentile within {n} real corpus songs per axis  (descriptive position, NOT quality)")
    print("=" * 78)
    last_cat = None
    extremes = []
    for m in prof.keys():
        cat = m.split("_", 1)[0]
        if cat != last_cat:
            print(f"\n-- {CAT_NAMES.get(cat, cat.upper())} --")
            last_cat = cat
        d = prof[m]
        flag = ""
        if d["percentile"] <= 5:
            flag = " ◀ low-extreme"; extremes.append((m, d["percentile"], "low"))
        elif d["percentile"] >= 95:
            flag = " ▶ high-extreme"; extremes.append((m, d["percentile"], "high"))
        name = m.split("_", 1)[1]
        print(f"  {name:<22} {bar(d['percentile'])} {d['percentile']:>3}%   "
              f"val={d['value']:<8} (corpus μ={d['corpus_mean']}){flag}")
    print("\n" + "-" * 78)
    if extremes:
        print("AT CORPUS EXTREMES (<=5% or >=95%): "
              + "; ".join(f"{m.split('_',1)[1]} {p}% ({d})" for m, p, d in extremes))
    else:
        print("No axis beyond the 5th/95th percentile — sits inside the corpus cloud.")
    # spread summary: a rich fingerprint varies across axes
    pcts = np.array([prof[m]["percentile"] for m in prof])
    print(f"profile spread: percentiles range {int(pcts.min())}–{int(pcts.max())}, "
          f"sd={pcts.std():.0f}  (high spread = distinct multi-axis fingerprint)")


if __name__ == "__main__":
    main()
