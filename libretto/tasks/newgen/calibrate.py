#!/usr/bin/env python3
"""calibrate.py — ADAPTIVE, corpus-calibrated newgen thresholds (per genre).

Why: the original newgen gate used fixed thresholds — C1 ≤3 extremes and genre-fit ≥6/8 split axes in band.
Checked against ground truth, those reject real corpus songs of the very genre being asked for: only ~20%
of real songs reach fit ≥6/8 (it is the binomial tail — P(≥6 of 8 independent 50%-bands) ≈ 14.5%), and the
C1 ≤3 budget rejects naturally-varied genres (film_score real-song pass 20%, electronic 56%). A gate that
fails the ground truth cannot fairly judge generation.

Fix: derive each threshold per genre from what REAL songs of that genre actually achieve, using the IDENTICAL
extreme/band-fit logic the gate uses. A generated piece must only be "as non-degenerate / as in-band as a
real song of this genre" — admit the same `ADMIT_FRACTION` of real songs.

  c1_budget(genre)    = quantile(real extreme-counts, ADMIT_FRACTION)        (ceil; floored 3, capped 6)
  fit_threshold(genre)= quantile(real band-occupancy, 1-ADMIT_FRACTION)      (floor; floored 3, capped 6)

The classifier leg of genre-fit (well-calibrated: ~70% real-song accept) is kept as an OR in the measure, so
fit_threshold is the loose band-fit floor, not the sole genre test. Thresholds are computed once and cached to
`data/newgen_calibration.json`; the gate loads the cache. Recompute with `python3 -m libretto.tasks.newgen.calibrate`.
"""
import json
from pathlib import Path

import numpy as np

import libretto
from libretto.core import Song, metrics_for
from libretto.core.copy_risk import piece_notes, slide_overlap, load_corpus

DATA = libretto.data_root()
CANON = json.loads((DATA / "corpus_distribution.json").read_text())
AXES = CANON["axes_order"]
COLS = {a: np.array(CANON["axes"][a]["values"], float) for a in AXES}
GC = CANON["genre_conditioned"]
SPLIT = list(GC.keys())
CACHE = DATA / "newgen_calibration.json"
# FIXED per-genre sample size: every genre is calibrated on the SAME number of real songs (= the smallest
# genre) sampled deterministically, so the copy-risk ceiling / c1-budget / fit quantiles are comparable
# across genres and sampling variance is uniform (no genre gets tighter estimates just for having more songs).
SAMPLE_N = 30
SAMPLE_SEED = 0
ADMIT_FRACTION = 0.85           # a generated piece need only be as clean as the worst ~15% of real songs
BUDGET_FLOOR, BUDGET_CAP = 3, 6
FIT_FLOOR, FIT_CAP = 3, 6
# copy: per-genre real-song copy ceiling (90th-pct of real copy_risk vs corpus, self-excluded) x tolerance,
# rounded. Idiom-heavy genres (latin montuno, etc.) legitimately reuse more, so the gate tracks the genre's
# upper-real-song copy — with 20% headroom above it, floored at the 0.30 standard (never stricter), capped at
# 0.45. p90 (not max) is robust: a single near-duplicate pair (the pop U2 0048/0110 at ~0.97) can't define
# the ceiling.
COPY_TOLERANCE = 1.20
COPY_PCTL = 0.90                # 90th pct — robust ceiling (1.0=max is hostage to one near-dup; lower=stricter)
COPY_FLOOR, COPY_CAP = 0.30, 0.45

_CAL = None


def _profile(path):
    m = metrics_for(Song(path), path)
    return {a: round(float((COLS[a] <= float(m[a])).mean() * 100)) for a in AXES}, m


def _extreme_count(prof, m, genre):
    """Genre-aware C1 extreme count — identical logic to the gate (split-axis genre-band exemption)."""
    n = 0
    for a in AXES:
        if prof[a] <= 5 or prof[a] >= 95:
            v = float(m[a])
            if a in GC and genre in GC[a] and GC[a][genre]["p25"] <= v <= GC[a][genre]["p75"]:
                continue
            n += 1
    return n


def _band_occupancy(m, genre):
    """# of the 8 split axes inside the target-genre [p25,p75] band — identical to the gate's genre_fit."""
    n = 0
    for ax in SPLIT:
        v = float(m[ax]); b = GC[ax][genre]
        ok = (v >= 11) if ax == "har_distinct_pc" and b["p75"] >= 12 else (b["p25"] <= v <= b["p75"])
        n += ok
    return n


_CORP = None
def _copy_vs_corpus_excl_self(sid):
    """Real song's max note-overlap vs the corpus EXCLUDING itself (mirrors copy_risk's corpus leg)."""
    global _CORP
    if _CORP is None:
        _CORP = load_corpus()
    gb, bag, tot = piece_notes(DATA / "grammar" / f"{sid}.txt")
    pre = sorted(((len(bag & b2) / max(1, len(bag)), s) for s, (bb, b2, t) in _CORP.items() if s != sid),
                 reverse=True)[:25]
    best = 0.0
    for _, s in pre:
        ov, _ = slide_overlap(gb, tot, _CORP[s][0])
        best = max(best, ov)
    return best


def compute(admit=ADMIT_FRACTION, write=True, sample_n=SAMPLE_N):
    """Compute per-genre calibration from the labeled corpus grammar files. One-time / on demand.

    Each genre is calibrated on a FIXED deterministic sample of `sample_n` real songs (equal N per genre),
    so copy-risk ceilings / budgets / fit thresholds are comparable across genres and sampling variance is
    uniform. (Prefer the parallel pre-builder; the copy step is ~16s/song.)"""
    import random
    key = json.loads((DATA / "answer_key" / "grammar_truth.json").read_text())
    by_genre = {}
    for s, v in key.items():
        g = v.get("genre")
        p = DATA / "grammar" / f"{s}.txt"
        if g and g in GC[SPLIT[0]] and p.exists():
            by_genre.setdefault(g, []).append(p)
    out = {"admit_fraction": admit, "copy_tolerance": COPY_TOLERANCE, "sample_n": sample_n, "genres": {}}
    for g, paths in sorted(by_genre.items()):
        ps = sorted(paths, key=lambda x: x.stem)
        if len(ps) > sample_n:                          # fixed equal-N sample per genre (deterministic)
            ps = random.Random(f"{SAMPLE_SEED}-{g}").sample(ps, sample_n)   # str seed => reproducible
        exts, occ, copies = [], [], []
        for p in ps:
            prof, m = _profile(p)
            exts.append(_extreme_count(prof, m, g))
            occ.append(_band_occupancy(m, g))
            copies.append(round(_copy_vs_corpus_excl_self(p.stem), 3))
        budget = int(np.ceil(np.quantile(exts, admit)))
        budget = max(BUDGET_FLOOR, min(BUDGET_CAP, budget))
        fitthr = int(np.floor(np.quantile(occ, 1 - admit)))
        fitthr = max(FIT_FLOOR, min(FIT_CAP, fitthr))
        copy_ceiling = float(np.quantile(copies, COPY_PCTL))           # the genre's idiomatic copy ceiling (p90)
        copy_thr = round(min(COPY_CAP, max(COPY_FLOOR, copy_ceiling * COPY_TOLERANCE)), 2)
        out["genres"][g] = {
            "n": len(paths), "c1_budget": budget, "fit_threshold": fitthr,
            "copy_threshold": copy_thr, "real_copy_ceiling": round(copy_ceiling, 3),
            "real_extreme_counts": sorted(exts), "real_band_occupancy": sorted(occ),
            "real_copy_risk": sorted(copies),
        }
    _add_clf_rank_thresholds(out, admit)
    if write:
        CACHE.write_text(json.dumps(out, indent=2))
    return out


def _add_clf_rank_thresholds(out, admit):
    """Genre-calibrated classifier-rank tolerance: for each genre, the ceil(quantile@admit) of the true-genre
    RANK that real songs achieve under the balanced-LogReg genre classifier (5-fold CV). A generated piece
    must classify at least this well. Uses the same balanced classifier as newgen_measure.classify()."""
    import numpy as _np
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import make_pipeline
    from sklearn.model_selection import cross_val_predict, StratifiedKFold
    fps = json.loads((DATA / "corpus_fps.json").read_text())
    key = json.loads((DATA / "answer_key" / "grammar_truth.json").read_text())
    X, y = [], []
    for s, v in fps.items():
        g = key.get(s, {}).get("genre")
        if g and g in out["genres"]:
            X.append(v); y.append(g)
    X = _np.array(X, float); y = _np.array(y)
    pipe = make_pipeline(StandardScaler(), LogisticRegression(max_iter=3000, C=1.0, class_weight="balanced"))
    proba = cross_val_predict(pipe, X, y, cv=StratifiedKFold(5, shuffle=True, random_state=0), method="predict_proba")
    pipe.fit(X, y); classes = list(pipe.classes_)
    for g in out["genres"]:
        gi = classes.index(g); idx = _np.where(y == g)[0]
        ranks = [list(_np.argsort(proba[i])[::-1]).index(gi) + 1 for i in idx]
        out["genres"][g]["clf_rank_threshold"] = int(_np.ceil(_np.quantile(ranks, admit)))
        out["genres"][g]["clf_rank_median"] = int(_np.median(ranks))
    out["clf"] = "balanced LogReg; clf_rank_threshold = ceil(quantile@%.2f of real-song true-genre CV ranks)" % admit


def calibration():
    global _CAL
    if _CAL is None:
        _CAL = json.loads(CACHE.read_text()) if CACHE.exists() else compute()
    return _CAL


def c1_budget(genre):
    """Max genre-aware C1 extremes a generated piece may have (genre-calibrated; default 3 if unknown)."""
    if not genre:
        return BUDGET_FLOOR
    return calibration()["genres"].get(genre, {}).get("c1_budget", BUDGET_FLOOR)


def fit_threshold(genre):
    """Min # of split axes in the genre band (AND'd with the genre-calibrated classifier-rank gate)."""
    if not genre:
        return FIT_FLOOR
    return calibration()["genres"].get(genre, {}).get("fit_threshold", FIT_FLOOR)


RANK_DEFAULT = 99   # unknown genre => no rank gate
def clf_rank_threshold(genre):
    """Max acceptable rank of the target genre in the balanced classifier's ranking — genre-calibrated to
    how real songs of the genre classify (ceil of the ADMIT_FRACTION quantile of real-song true-genre ranks).
    Genres structure separates cleanly (electronic/jazz) => top-1..2; ambiguous genres (latin/blues) tolerate
    more. A generated piece need only classify as well as the worst ~15% of real songs of its genre."""
    if not genre:
        return RANK_DEFAULT
    return calibration()["genres"].get(genre, {}).get("clf_rank_threshold", RANK_DEFAULT)


def copy_threshold(genre):
    """Max copy_risk: genre's real-song copy ceiling x tolerance (rounded), floored at the 0.30 standard.
    Adaptive per genre — idiom-heavy genres get more room — but never stricter than 0.30. Default 0.30."""
    if not genre:
        return COPY_FLOOR
    return calibration()["genres"].get(genre, {}).get("copy_threshold", COPY_FLOOR)


if __name__ == "__main__":
    cal = compute()
    print(f"newgen calibration (admit {cal['admit_fraction']:.0%} of real songs, copy x{cal['copy_tolerance']}) -> {CACHE}")
    print(f"  {'genre':<20}{'n':>4}{'C1 budget':>11}{'fit_thresh':>12}{'copy_thr':>10}{'(real p90)':>12}")
    for g, d in cal["genres"].items():
        flag = "  <- near-dup inflated (capped)" if d["real_copy_ceiling"] >= 0.5 else ""
        print(f"  {g:<20}{d['n']:>4}{d['c1_budget']:>11}{d['fit_threshold']:>12}{d['copy_threshold']:>10}{d['real_copy_ceiling']:>12}{flag}")
