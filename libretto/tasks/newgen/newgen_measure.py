#!/usr/bin/env python3
"""newgen_measure.py — score a REAL from-scratch piece (no source), with ADAPTIVE genre-calibrated criteria.

Criteria (no coherence/boundary — there is no source):
  NON-DEGENERATE  genre-aware C1 extremes (≤5/≥95 pct, split-axis genre-band exemption) ≤ c1_budget(genre)
  FULL-LENGTH     C2 bars in [64,179]
  GENUINELY-NEW   note-level copy_risk vs corpus < 0.30 (strict from-scratch gate)
  GENRE-FIT       (genre mode) classifier top-genre == target  OR  split-axes-in-band ≥ fit_threshold(genre)

The C1 budget and band-fit floor are CALIBRATED per genre against real corpus songs (see calibrate.py): a
generated piece need only be as non-degenerate / as in-band as a real song of the genre. The classifier
(LogReg on the labeled corpus fingerprints) is the primary genre test; the band-fit floor is a loose backstop.

  python3 -m libretto.tasks.newgen.newgen_measure <piece.txt> <genre_name|brief>
"""
import json, sys
from pathlib import Path

import numpy as np

import libretto
from libretto.core import Song, metrics_for, copy_risk
from . import calibrate as cal

DATA = libretto.data_root()
CANON = json.loads((DATA / "corpus_distribution_314.json").read_text())
AXES = CANON["axes_order"]; COLS = {a: np.array(CANON["axes"][a]["values"], float) for a in AXES}
GC = CANON["genre_conditioned"]; SPLIT = list(GC.keys())
KEY = json.loads((DATA / "answer_key" / "grammar_truth.json").read_text())
FPS = json.loads((DATA / "corpus_fps.json").read_text())
OUT = Path("compositions/newgen");


def fp(path):
    m = metrics_for(Song(path), path)
    prof = {a: round(float((COLS[a] <= float(m[a])).mean() * 100)) for a in AXES}
    return prof, m


def ga_extremes(prof, m, genre):
    out = []
    for a in AXES:
        if prof[a] <= 5 or prof[a] >= 95:
            v = float(m[a])
            if genre and a in GC and genre in GC[a] and GC[a][genre]["p25"] <= v <= GC[a][genre]["p75"]:
                continue
            out.append((a.split("_", 1)[1], prof[a]))
    return out


_CLF = None
def classify(prof):
    """Train LogReg on the labeled corpus fingerprints; predict this piece's top genre (cached)."""
    global _CLF
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    if _CLF is None:
        X, y = [], []
        for s, vec in FPS.items():
            g = KEY.get(s, {}).get("genre")
            if g:
                X.append(vec); y.append(g)
        X = np.array(X, float); sc = StandardScaler().fit(X)
        clf = LogisticRegression(max_iter=3000, C=1.0).fit(sc.transform(X), y)
        _CLF = (sc, clf)
    sc, clf = _CLF
    v = sc.transform([[prof[a] for a in AXES]])
    probs = clf.predict_proba(v)[0]; order = np.argsort(probs)[::-1]
    return [(clf.classes_[i], round(float(probs[i]), 2)) for i in order[:3]]


def measure(piece, target):
    """Return the newgen verdict dict (importable; the CLI wraps this)."""
    genre = None if target == "brief" else target
    prof, m = fp(piece)
    bars = len(sorted({e["bar"] for e in Song(piece).events}))
    top = classify(prof)
    # Brief mode has no target genre, so non-degeneracy is judged against the BEST-FIT genre (the classifier's
    # top read): that grants the genre-aware C1 budget + split-axis band exemptions a genre-free piece deserves
    # (otherwise idiomatic traits read as "extreme" under a genre-blind frame, over-failing real-sounding music).
    c1_genre = genre if genre else top[0][0]
    budget = cal.c1_budget(c1_genre); fit_thr = cal.fit_threshold(genre); copy_thr = cal.copy_threshold(c1_genre)
    ext = ga_extremes(prof, m, c1_genre); c1 = len(ext) <= budget
    c2 = 64 <= bars <= 179
    risk = copy_risk(piece, vs_corpus=True, threshold=copy_thr); new = risk["copy_risk"] < copy_thr
    fit = None; clf_match = None
    if genre:
        inb = []
        for ax in SPLIT:
            v = float(m[ax]); b = GC[ax][genre]
            ok = (v >= 11) if ax == "har_distinct_pc" and b["p75"] >= 12 else (b["p25"] <= v <= b["p75"])
            inb.append((ax, ok))
        fit = sum(ok for _, ok in inb)
        clf_match = top[0][0] == genre
        genre_ok = clf_match or fit >= fit_thr
        verdict = c1 and c2 and new and genre_ok
    else:
        verdict = c1 and c2 and new
    return dict(piece=Path(piece).name, target=target, bars=bars, c1_ext=len(ext), c1_budget=budget, c1=c1,
                c2=c2, copy_risk=risk["copy_risk"], copy_threshold=copy_thr, copy_song=risk["max_corpus"]["song"],
                new=new, classifier_top=top, clf_match=clf_match, genre_fit=fit, fit_threshold=fit_thr,
                best_fit_genre=c1_genre, extremes=ext, verdict=bool(verdict))


def main(piece, target):
    s = measure(piece, target)
    print(f"=== NEWGEN MEASURE (adaptive) — {s['piece']} — target={target} ===")
    print(f"  bars={s['bars']}  (C2 [64,179]: {'Y' if s['c2'] else 'N'})")
    print(f"  NON-DEGENERATE C1 extremes={s['c1_ext']} (budget {s['c1_budget']}: {'Y' if s['c1'] else 'N'}) {s['extremes'] if s['extremes'] else ''}")
    print(f"  GENUINELY-NEW  copy_risk={s['copy_risk']:.2f} ({s['copy_song']})  (<{s['copy_threshold']} genre-calibrated: {'Y' if s['new'] else 'N'})")
    print(f"  CLASSIFIER top-3: {s['classifier_top']}")
    if s["target"] != "brief":
        print(f"  GENRE-FIT      split axes in band: {s['genre_fit']}/8 (floor {s['fit_threshold']})  | classifier match: {'Y' if s['clf_match'] else 'N'}")
    why = []
    if not s["c1"]: why.append("non-degen")
    if not s["c2"]: why.append("length")
    if not s["new"]: why.append("new")
    if s["target"] != "brief" and not (s["clf_match"] or s["genre_fit"] >= s["fit_threshold"]): why.append("genre")
    print(f"  >>> {'PASS' if s['verdict'] else 'FAIL: ' + ', '.join(why)}")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{Path(piece).stem}_measure.json").write_text(json.dumps(s, indent=2, default=float))
    return s


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
