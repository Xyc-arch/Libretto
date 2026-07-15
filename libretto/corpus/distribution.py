"""libretto.corpus.distribution — rebuild the canonical distribution ("statistical cloud") over a corpus.

v3: the coordinate system is the 33 axes DISCOVERED by the axis_evolve loop (libretto.core.axes_v3),
replacing the hand-authored 28 metric_discovery axes + within_song_variation (preserved in git history).
Fingerprints every song on the 33 axes, then writes the frozen data artifacts to a STAGING dir (never
the live frozen data — that's a deliberate finalize step):

  metric_corpus.json         — {metrics:[33], n_real, corpus:{ax:[values]}, categories:{ax:cat}}
  corpus_distribution.json   — 33 axes: per-axis genre-balanced empirical CDF + breakpoints + genre bands
  corpus_fps.json            — per-song 33-dim PERCENTILE coordinate vector (retrieval + classifier)

Rebuilding re-maps every downstream coordinate => a DELIBERATE frozen-core (CORE MAJOR) change.
Fingerprinting is parallel (--workers); the worker is top-level so it is picklable under spawn.

  python -m libretto.corpus.distribution --grammar DIR --truth truth.json --out-dir STAGE [--workers 8]
"""
import argparse
import json
from multiprocessing import Pool
from pathlib import Path

import numpy as np

from libretto.core import Song
from libretto.core import axes_v3
from libretto.core import metric_discovery as md      # md.describe: generic distribution-shape describer


def bp(a):
    a = np.asarray(a, float)
    p = np.percentile(a, [5, 25, 50, 75, 95])
    return {"p5": round(float(p[0]), 4), "p25": round(float(p[1]), 4), "p50": round(float(p[2]), 4),
            "p75": round(float(p[3]), 4), "p95": round(float(p[4]), 4),
            "mean": round(float(a.mean()), 4), "sd": round(float(a.std()), 4),
            "min": round(float(a.min()), 4), "max": round(float(a.max()), 4),
            "band": [round(float(p[1]), 4), round(float(p[3]), 4)], "n": int(len(a))}


def _fp_one(job):
    """Worker: fingerprint one song on the 33 v3 axes -> (sid, {ax:val}) or (sid, None, err).
    Applies the SAME admission filter as the axis_evolve discovery corpus (>=2 voices, 8..400 bars)
    so the distribution is built over exactly the songs the axes were discovered on."""
    sid, path, min_bars, max_bars = job
    try:
        s = Song(path)
        nvoices = len([v for v in s.voices if s.voice_events(v)])
        if nvoices < 2 or not (min_bars <= s.n_bars <= max_bars):
            return sid, None, "filtered (single-voice or out-of-range bars)"
        m = axes_v3.metrics_for(s)
        if not m:
            return sid, None, "empty metrics"
        return sid, {k: float(v) for k, v in m.items()}, None
    except Exception as e:  # noqa: BLE001
        return sid, None, str(e)[:70]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--grammar", required=True)
    ap.add_argument("--truth", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--date", default="2026-07-06")
    ap.add_argument("--min-bars", type=int, default=8)
    ap.add_argument("--max-bars", type=int, default=400)
    a = ap.parse_args(argv)

    gdir = Path(a.grammar)
    truth = json.loads(Path(a.truth).read_text())
    out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)

    # admission filter (match the frozen-corpus rule: drop single-voice + out-of-range bar counts)
    jobs = []
    for f in sorted(gdir.glob("song_*.txt")):
        if truth.get(f.stem, {}).get("genre"):
            jobs.append((f.stem, str(f), a.min_bars, a.max_bars))

    # ---- parallel fingerprint on the 33 axes ----
    fp = {}; fails = []
    with Pool(a.workers, maxtasksperchild=20) as pool:
        done = 0
        for sid, m, err in pool.imap_unordered(_fp_one, jobs, chunksize=1):
            done += 1
            if m is None:
                fails.append((sid, err)); continue
            fp[sid] = m
            if done % 200 == 0:
                print(f"  ...fingerprinted {done}/{len(jobs)} ({len(fails)} fail)", flush=True)
    if fails:
        print(f"  FP FAILS ({len(fails)}): {fails[:5]}")
    sids = sorted(fp)
    AXES = list(axes_v3.REGISTRY)                       # the 33 discovered axes, in registry order
    axes_order = AXES                                   # no separate WSV axis in v3
    missing = [ax for ax in AXES if any(ax not in fp[s] for s in sids)]
    assert not missing, f"axes missing from some songs: {missing[:5]}"
    genre_of = {s: (truth.get(s, {}).get("genre") or "unknown") for s in sids}
    genres = sorted(set(genre_of.values()))

    # ---- metric_corpus.json ----
    corpus = {ax: [fp[s][ax] for s in sids] for ax in AXES}
    categories = {ax: ax.split("_", 1)[1].split("_")[0] if "_" in ax else ax for ax in AXES}
    (out / "metric_corpus.json").write_text(json.dumps(
        {"metrics": AXES, "n_real": len(sids), "corpus": corpus, "categories": categories}))

    # ---- corpus_distribution.json ----
    gv = {ax: {} for ax in axes_order}
    for ax in axes_order:
        for s in sids:
            gv[ax].setdefault(genre_of[s], []).append(fp[s][ax])

    # GENRE-BALANCED global distribution: resample each genre's sorted values to K points (K = largest
    # genre's count) so every genre contributes equally to the global CDF/percentiles (removes skew).
    K = max(len(v) for v in gv[axes_order[0]].values())
    def _balanced(per_genre):
        cols = []
        for g, vals in per_genre.items():
            v = np.sort(np.asarray(vals, float)); n = len(v)
            idx = (np.arange(K) * n // K).clip(0, n - 1)
            cols.append(v[idx])
        return np.sort(np.concatenate(cols))

    axes = {}
    for ax in axes_order:
        arr = _balanced(gv[ax])
        d = md.describe(arr)
        rec = bp(arr)
        rec["values"] = [float(x) for x in arr]
        rec["shape"] = "DEGENERATE" if d["degenerate"] else d["shape"]
        rec["bimodality_coef"] = round(float(d["bc"]), 3)
        rec["category"] = categories[ax]
        rec["n_songs"] = len(sids)
        axes[ax] = rec
    # per-genre bands for EVERY axis (genre-adaptive scoring); v3 splits all axes by genre
    genre_conditioned = {ax: {g: bp(gv[ax][g]) for g in genres if len(gv[ax].get(g, [])) >= 4}
                         for ax in axes_order}
    doc = {
        "header": {
            "reference": "FROZEN CANONICAL corpus distribution — all downstream fingerprinting scores against this",
            "n_songs": len(sids), "n_axes": len(axes_order), "excludes": [],
            "created": a.date, "grid": "adaptive",
            "source": "libretto.core.axes_v3.metrics_for (33 discovered axes) over grammar/ (real songs)",
            "balancing": "GENRE-BALANCED global distribution: each genre resampled to K=max-genre-count points so "
                         "genres contribute equally to the global CDF/percentiles (removes corpus-imbalance skew). "
                         "Per-genre bands (genre_conditioned) are raw.",
            "scoring": "percentile(v) = 100 * mean(values <= v) using the per-axis 'values' array (genre-balanced empirical CDF)",
            "axis_system": "v3 — 33 axes discovered from scratch by the axis_evolve self-loop",
            "regenerate_with": "python -m libretto.corpus.distribution (deliberate only — changes all coordinates)",
        },
        "axes_order": axes_order,
        "genres": {g: sum(1 for s in sids if genre_of[s] == g) for g in genres},
        "split_axes": axes_order,
        "axes": axes,
        "genre_conditioned": genre_conditioned,
    }
    (out / "corpus_distribution.json").write_text(json.dumps(doc))

    # ---- corpus_fps.json (per-song 33-dim percentile coords vs the empirical CDF just built) ----
    cols = {ax: np.array(axes[ax]["values"], float) for ax in axes_order}
    fps = {s: [round(float((cols[ax] <= fp[s][ax]).mean() * 100)) for ax in axes_order] for s in sids}
    (out / "corpus_fps.json").write_text(json.dumps(fps))

    # ---- per-genre extreme BUDGET: how many of the N axes a REAL song of the genre has outside its own
    # genre p5/p95 band. Calibrates the composer's convergence gate to real music (a typical real song
    # sits ~N*0.10 axes outside its 90% bands), instead of an arbitrary flat threshold. Equivalent in
    # fps-percentile space to counting vs the raw genre_conditioned bands (monotone per-axis transform).
    X = np.array([fps[s] for s in sids], float)
    yg = np.array([genre_of[s] for s in sids])
    budget = {}
    for g in genres:
        Xg = X[yg == g]
        if len(Xg) < 4:
            continue
        lo, hi = np.percentile(Xg, 5, axis=0), np.percentile(Xg, 95, axis=0)
        ext = ((Xg < lo) | (Xg > hi)).sum(axis=1)
        budget[g] = {"median": int(np.median(ext)), "p75": int(np.percentile(ext, 75)),
                     "mean": round(float(ext.mean()), 1), "n": int(len(ext))}
    doc["genre_extreme_budget"] = budget
    (out / "corpus_distribution.json").write_text(json.dumps(doc))   # rewrite with the budget included

    print(f"\nDONE -> {out}")
    print(f"  songs: {len(sids)} ({len(fails)} fp-fail); axes: {len(axes_order)} (v3 discovered)")
    print(f"  genres: " + ", ".join(f"{g}={doc['genres'][g]}" for g in genres))


if __name__ == "__main__":
    main()
