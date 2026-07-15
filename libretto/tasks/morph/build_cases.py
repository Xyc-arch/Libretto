#!/usr/bin/env python3
"""build_cases — pkg-native, reproducible CROSS-GENRE morph case sampler.

Builds a genre-BALANCED set of morph cases A → B, each a pair of real songs from two DIFFERENT genres, so the
morph metric's genre-shift lens (P(source) falls / P(target) rises) has something to detect. Balance by
construction: a single cyclic permutation of the 11 genres → 11 ordered pairs (g0→g1, g1→g2, …, g10→g0), so
every genre is the SOURCE exactly once and the TARGET exactly once. Each genre's endpoint is its most-typical
EXEMPLAR — the song nearest the genre centroid in 39-axis fingerprint space (bars 48–200) — so the endpoints
read strongly in-genre and the classifier can see the shift.

    python -m libretto.tasks.morph.build_cases --seed 1 --out compositions/morph/cases

Each case.json (schema compatible with morph_setup) carries fpA, fpB, the per-segment interpolated targets,
the top morph axes (which must glide), and the key/tempo/genre plan. Uses corpus_fps (the shipped 39-axis
percentile fingerprints) — NOT metric_discovery — so it matches the metric + corpus_distribution.
"""
import argparse
import json
import re
from collections import Counter
from pathlib import Path

import numpy as np

import libretto

DATA = libretto.data_root()
GRAMMAR = DATA / "grammar"
CANON = json.loads((DATA / "corpus_distribution.json").read_text())
AXES = CANON["axes_order"]
TRUTH = json.loads((DATA / "answer_key" / "grammar_truth.json").read_text())
CFP = {s: np.array(v, float) for s, v in json.loads((DATA / "corpus_fps.json").read_text()).items()}
GENRES = ["pop_rock", "funk_soul_rnb", "electronic_dance", "jazz", "folk_country", "classical",
          "metal", "hiphop_rap", "reggae_ska", "latin", "blues_gospel"]
BARS_RANGE = (48, 200)
DEFAULT_OUT = "compositions/morph/cases"


def _bars(sid):
    b = TRUTH.get(sid, {}).get("bars"); return int(b) if str(b).isdigit() else 0


def _hdr(sid):
    return (GRAMMAR / f"{sid}.txt").read_text().splitlines()[0]


def _hv(h, tag, cast=str):
    m = re.search(rf"{tag}:\s*([^|]+)", h)
    return cast(m.group(1).strip()) if m else (0 if cast is int else "")


def genre_exemplars(seed=0):
    """One UNAMBIGUOUS exemplar per genre = the eligible song the genre classifier is most confident reads as
    that genre (bars 48-200, has a corpus fingerprint). Morph endpoints must be clear genre anchors so the
    genre-shift lens can detect the crossing — so we select for max P(own genre), not mere typicality. seed>0
    picks among the top-5 most-confident candidates for variety; seed=0 = the single most confident.
    Returns {genre: sid}."""
    from libretto.tasks.morph.morph_metric import _classifier
    clf, genres = _classifier()
    rng = np.random.RandomState(seed)
    out = {}
    for g in GENRES:
        cand = [s for s, v in TRUTH.items()
                if v.get("genre") == g and s in CFP and BARS_RANGE[0] <= _bars(s) <= BARS_RANGE[1]]
        if not cand:
            raise ValueError(f"no eligible exemplar for genre {g}")
        gi = genres.index(g)
        proba = clf.predict_proba(np.array([CFP[s] for s in cand], float))[:, gi]
        ranked = [cand[i] for i in np.argsort(-proba)]     # most-confidently-in-genre first
        out[g] = ranked[0] if seed == 0 else ranked[int(rng.randint(0, min(5, len(ranked))))]
    return out


def cross_genre_pairs(seed=0):
    """A cyclic permutation of the genres → ordered (source_genre, target_genre) pairs. Every genre is source
    once and target once (perfectly balanced, all cross-genre)."""
    order = list(GENRES)
    if seed > 0:
        np.random.RandomState(seed).shuffle(order)
    return [(order[i], order[(i + 1) % len(order)]) for i in range(len(order))]


def build_case(A, B, S=6, seg_bars=9):
    """One morph case A→B from the shipped fingerprints (schema-compatible with morph_setup)."""
    fa = {a: int(CFP[A][i]) for i, a in enumerate(AXES)}
    fb = {a: int(CFP[B][i]) for i, a in enumerate(AXES)}
    targets = [{a: round(fa[a] + (s / (S - 1)) * (fb[a] - fa[a])) for a in AXES} for s in range(S)]
    morph_axes = sorted(AXES, key=lambda a: abs(fa[a] - fb[a]), reverse=True)[:10]
    ha, hb = _hdr(A), _hdr(B)
    return dict(cid=f"{A}_{B}", A=A, B=B, S=S, seg_bars=seg_bars, total_bars=S * seg_bars,
                fpA=fa, fpB=fb, targets=targets, morph_axes=morph_axes,
                keyA=_hv(ha, "KEY"), keyB=_hv(hb, "KEY"), tempoA=_hv(ha, "TEMPO", int), tempoB=_hv(hb, "TEMPO", int),
                genreA=TRUTH[A].get("genre"), genreB=TRUTH[B].get("genre"),
                titleA=TRUTH[A].get("title"), titleB=TRUTH[B].get("title"),
                axis_gap=int(round(float(np.mean(np.abs(CFP[A] - CFP[B]))))))


def build_cases(seed=0, out=DEFAULT_OUT, S=6, seg_bars=9):
    """Build a genre-balanced cross-genre morph case set. Returns the cases dict {cid: case}. Writes each
    morph_<A>_<B>_case.json + a cases.json index under `out`."""
    outp = Path(out); outp.mkdir(parents=True, exist_ok=True)
    ex = genre_exemplars(seed)
    pairs = cross_genre_pairs(seed)
    cases = {}
    for gA, gB in pairs:
        c = build_case(ex[gA], ex[gB], S, seg_bars)
        cases[c["cid"]] = c
        (outp / f"morph_{c['cid']}_case.json").write_text(json.dumps(c, indent=2))
    (outp / "cases.json").write_text(json.dumps(cases, indent=2))
    # BALANCE GUARANTEE: every genre is source once and target once, all cross-genre
    srcs = Counter(c["genreA"] for c in cases.values()); tgts = Counter(c["genreB"] for c in cases.values())
    assert all(srcs[g] == 1 and tgts[g] == 1 for g in GENRES), f"unbalanced: src {srcs} tgt {tgts}"
    assert all(c["genreA"] != c["genreB"] for c in cases.values()), "a pair is not cross-genre"
    return cases


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seed", type=int, default=0, help="0 = most-typical exemplars + canonical cycle; >0 = fresh draw")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--segments", type=int, default=6)
    ap.add_argument("--seg-bars", type=int, default=9)
    a = ap.parse_args()
    cases = build_cases(seed=a.seed, out=a.out, S=a.segments, seg_bars=a.seg_bars)
    print(f"built {len(cases)} cross-genre morph cases (seed {a.seed}) -> {a.out}")
    for c in cases.values():
        print(f"  {c['cid']:26s} {c['genreA']:16s} -> {c['genreB']:16s}  axis-gap {c['axis_gap']:>2}  "
              f"key {c['keyA']}->{c['keyB']} tempo {c['tempoA']}->{c['tempoB']}")
    print("balanced: every genre is source once and target once, all cross-genre OK")


if __name__ == "__main__":
    main()
