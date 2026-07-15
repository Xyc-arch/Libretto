#!/usr/bin/env python3
"""morph_metric — score a stylistic MORPH A -> B on the current 39-axis substrate.

A morph is a single piece whose STYLE travels from source A to target B across S equal segments. A good
morph is (1) GRADUAL — the trajectory moves monotonically and in EVEN steps from A to B (no jump, no
backtrack), and (2) a genuine GENRE SHIFT — a genre classifier on the 39-axis fingerprints reads the early
segments as A's genre and the late ones as B's, with the target-genre probability rising and the source-genre
probability falling and a clean crossover in between. Plus the usual anchors: endpoints near A/B, genuinely
new (not a spliced medley), each segment non-degenerate.

Two lenses, both reported and combined into a single `morph_score` in [0,1]:
  • GRADUALITY  — axis-fingerprint trajectory: monotonic progress A->B, even step sizes, anchored ends.
  • GENRE SHIFT — classifier P(source) falls / P(target) rises monotonically, with a mid-morph crossover.

    python -m libretto.tasks.morph.morph_metric <morph.txt> <A_sid> <B_sid> [S=6]

Reuses libretto.core.metrics_for (the 39 axis_* metrics — NOT metric_discovery's raw har_/form_ keys) so the
fingerprint matches corpus_distribution, and trains the same LogisticRegression genre classifier used by the
newgen steer (on corpus_fps + grammar_truth genres).
"""
import argparse
import json
import re
from functools import lru_cache
from pathlib import Path

import numpy as np

import libretto
from libretto.core import metrics_for, Song, copy_risk

DATA = libretto.data_root()
GRAMMAR = DATA / "grammar"
CANON = json.loads((DATA / "corpus_distribution.json").read_text())
AXES = CANON["axes_order"]
COLS = {a: np.array(CANON["axes"][a]["values"], float) for a in AXES}
TRUTH = json.loads((DATA / "answer_key" / "grammar_truth.json").read_text())
# whole-piece / length-family axes are noisy on a short segment — excluded from the graduality trajectory
LENGTH_AXES = {"axis_note_density_bar_variability", "axis_bar_pitch_range_mean"}
MORPH_MIN_DIFF = 15   # an axis counts as a "morph axis" only if A and B differ by >= this many percentiles


# ── genre classifier (trained once on corpus fingerprints; same recipe as the newgen steer) ─────────────
@lru_cache(maxsize=1)
def _classifier():
    from sklearn.linear_model import LogisticRegression
    fps = json.loads((DATA / "corpus_fps.json").read_text())
    sids = [s for s in fps if TRUTH.get(s, {}).get("genre")]
    x = np.array([fps[s] for s in sids], float)
    y = np.array([TRUTH[s]["genre"] for s in sids])
    clf = LogisticRegression(max_iter=2000, class_weight="balanced").fit(x, y)
    return clf, list(clf.classes_)


def _fp(path):
    m = metrics_for(Song(path), path)
    return np.array([round(float((COLS[a] <= float(m[a])).mean() * 100)) for a in AXES], float)


def _dist(a, b):
    return float(np.mean(np.abs(a - b)))


def _spearman(y):
    """Spearman rank corr of y vs the segment index 0..len-1 (monotonicity of a trajectory)."""
    from scipy.stats import spearmanr
    if len(y) < 2 or len(set(y)) == 1:
        return 0.0
    r = spearmanr(range(len(y)), y).correlation
    return 0.0 if r is None or np.isnan(r) else float(r)


def split_segments(path, S, out_dir):
    """Write S equal-bar sub-grammars (header + that bar range, renumbered @1..) and return their paths."""
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    lines = Path(path).read_text().splitlines()
    head = [l for l in lines[:8] if not l.startswith("@")][:2]
    blocks, cur = [], None
    for l in lines:
        if l.startswith("@"):
            if cur is not None:
                blocks.append(cur)
            cur = [l]
        elif cur is not None:
            cur.append(l)
    if cur is not None:
        blocks.append(cur)
    n = len(blocks); per = max(1, n // S); segs = []
    for s in range(S):
        lo = s * per; hi = (s + 1) * per if s < S - 1 else n
        bb = blocks[lo:hi]
        out = [re.sub(r"BARS:\s*\d+", f"BARS: {len(bb)}", head[0]), head[1] if len(head) > 1 else "VOICES: V"]
        for i, blk in enumerate(bb, 1):
            x = list(blk); x[0] = re.sub(r"^@\d+", f"@{i}", x[0]); out.extend(x)
        p = out_dir / f"_seg{s}.txt"; p.write_text("\n".join(out) + "\n"); segs.append(p)
    return segs


def graduality(seg_fps, fpA, fpB):
    """Trajectory graduality on the MORPH subspace (axes that actually differ A->B). Returns the per-segment
    progress (0=A .. 1=B) and how monotonic + EVENLY-STEPPED + anchored the glide is."""
    ridx = [i for i, a in enumerate(AXES)
            if a not in LENGTH_AXES and abs(fpA[i] - fpB[i]) >= MORPH_MIN_DIFF]
    if not ridx:                                   # A and B barely differ — no morph axes
        ridx = [i for i, a in enumerate(AXES) if a not in LENGTH_AXES]
    faR, fbR = fpA[ridx], fpB[ridx]
    prog = []
    for v in seg_fps:
        vr = v[ridx]
        dA, dB = float(np.mean(np.abs(vr - faR))), float(np.mean(np.abs(vr - fbR)))
        prog.append(dA / max(1e-9, dA + dB))
    prog = np.array(prog)
    steps = np.diff(prog)
    span = float(prog[-1] - prog[0])
    ideal = span / max(1, len(prog) - 1)
    # EVENNESS = 1 - coefficient-of-variation of the forward steps (only meaningful when advancing)
    fwd = steps[steps > 0]
    evenness = float(max(0.0, 1.0 - (np.std(steps) / (abs(np.mean(steps)) + 1e-9)))) if len(steps) else 0.0
    max_jolt = float(max(steps) / ideal) if ideal > 1e-6 and len(steps) else 0.0     # largest step / ideal
    backtracks = int((steps < -0.05).sum())                                          # meaningful reversals
    mono = _spearman(prog)                                                            # want ~ +1
    anchored = bool(prog[0] < 0.40 and prog[-1] > 0.60)
    # 0-1 graduality score: monotonic AND spans AND even AND anchored
    score = float(np.mean([
        max(0.0, mono),                                   # monotonic rise
        min(1.0, span / 0.6),                             # spans the space (0.6 -> full credit)
        evenness,                                         # even steps (the "gradual" core)
        1.0 if anchored else 0.0,                         # endpoints anchored
    ]))
    return dict(progress=[round(float(p), 3) for p in prog], span=round(span, 3),
                monotonic_spearman=round(mono, 3), evenness=round(evenness, 3),
                max_jolt=round(max_jolt, 2), backtracks=backtracks, anchored=anchored,
                morph_axes=[AXES[i].split("_", 1)[1] for i in ridx], score=round(score, 3))


def genre_shift(seg_fps, gA, gB):
    """Classifier genre-shift: P(source) should fall and P(target) rise monotonically across the morph, with
    a clean crossover, and the endpoints should READ AS A then B. n/a when A and B share a genre."""
    clf, genres = _classifier()
    P = clf.predict_proba(np.array(seg_fps, float))       # (S, n_genres)
    read = [genres[int(np.argmax(p))] for p in P]
    same_genre = (gA == gB)
    pA = P[:, genres.index(gA)] if gA in genres else np.zeros(len(P))
    pB = P[:, genres.index(gB)] if gB in genres else np.zeros(len(P))
    # crossover: first segment where target prob overtakes source prob (after starting below)
    cross = next((s for s in range(len(P)) if pB[s] >= pA[s]), None)
    cross_frac = round(cross / max(1, len(P) - 1), 2) if cross is not None else None
    pB_rise = _spearman(pB)                                # want ~ +1
    pA_fall = _spearman(pA)                                # want ~ -1
    ends_read = bool(read[0] == gA and read[-1] == gB)
    if same_genre:
        score = float(np.mean([1.0 if read[0] == gA else 0.0, 1.0 if read[-1] == gB else 0.0]))
    else:
        score = float(np.mean([
            max(0.0, pB_rise),                            # target rises
            max(0.0, -pA_fall),                           # source falls
            1.0 if cross is not None else 0.0,            # a handover happens
            1.0 if ends_read else 0.0,                    # endpoints read as A then B
        ]))
    return dict(source_genre=gA, target_genre=gB, same_genre=same_genre,
                p_source=[round(float(x), 3) for x in pA], p_target=[round(float(x), 3) for x in pB],
                reads_as=read, target_rise_spearman=round(pB_rise, 3),
                source_fall_spearman=round(pA_fall, 3), crossover_seg=cross, crossover_frac=cross_frac,
                endpoints_read_A_to_B=ends_read, score=round(score, 3))


def morph_metric(path, A, B, S=6, source_genre=None, target_genre=None, tmp_dir=None):
    """Full morph metric. Returns a dict with the graduality + genre-shift lenses, novelty/non-degeneracy
    anchors, and a combined `morph_score` in [0,1]."""
    gA = source_genre or TRUTH.get(A, {}).get("genre")
    gB = target_genre or TRUTH.get(B, {}).get("genre")
    fpA = _fp(GRAMMAR / f"{A}.txt") if (GRAMMAR / f"{A}.txt").exists() else None
    fpB = _fp(GRAMMAR / f"{B}.txt") if (GRAMMAR / f"{B}.txt").exists() else None
    tmp = Path(tmp_dir) if tmp_dir else (Path(path).parent / "_morph_segs")
    segs = split_segments(path, S, tmp)
    seg_fps = [_fp(p) for p in segs]
    for p in segs:
        p.unlink(missing_ok=True)
    if fpA is None:
        fpA = seg_fps[0]
    if fpB is None:
        fpB = seg_fps[-1]

    grad = graduality(seg_fps, fpA, fpB)
    shift = genre_shift(seg_fps, gA, gB)
    # anchors: genuinely NEW (not a medley of A/B or corpus material) + each segment non-degenerate
    riskA = copy_risk(path, cited=[A], vs_corpus=False, threshold=0.30).get("max_cited", {}).get("overlap", 0.0)
    riskB = copy_risk(path, cited=[B], vs_corpus=False, threshold=0.30).get("max_cited", {}).get("overlap", 0.0)
    riskC = copy_risk(path, vs_corpus=True, threshold=0.30).get("max_corpus", {}).get("overlap", 0.0)
    new = bool(max(riskA, riskB, riskC) < 0.30)
    # combined score: graduality x genre-shift, gated (soft) by novelty
    combined = round(grad["score"] * shift["score"] * (1.0 if new else 0.7), 3)
    verdict = bool(grad["score"] >= 0.6 and shift["score"] >= 0.6 and new)
    return dict(A=A, B=B, S=S, morph_score=combined, verdict=verdict,
                graduality=grad, genre_shift=shift,
                genuinely_new=new, copy_A=round(riskA, 3), copy_B=round(riskB, 3), copy_corpus=round(riskC, 3))


def _print(r):
    g, s = r["graduality"], r["genre_shift"]
    print(f"=== MORPH METRIC — {r['A']} -> {r['B']} ({r['S']} segments) ===")
    print(f"  GRADUALITY  score {g['score']}  | progress {g['progress'][0]}->{g['progress'][-1]} "
          f"(span {g['span']}) | monotonic ρ={g['monotonic_spearman']} evenness={g['evenness']} "
          f"max_jolt={g['max_jolt']}x backtracks={g['backtracks']} anchored={g['anchored']}")
    print(f"              morph axes: {', '.join(g['morph_axes'][:8])}{'…' if len(g['morph_axes'])>8 else ''}")
    print(f"  GENRE SHIFT score {s['score']}  | {s['source_genre']} -> {s['target_genre']}"
          f"{'  (same genre — n/a)' if s['same_genre'] else ''}")
    print(f"              P(target) {s['p_target']}  rise ρ={s['target_rise_spearman']}")
    print(f"              P(source) {s['p_source']}  fall ρ={s['source_fall_spearman']}")
    print(f"              reads-as: {' -> '.join(s['reads_as'])}")
    print(f"              crossover @seg {s['crossover_seg']} ({s['crossover_frac']}) | ends read A->B: {s['endpoints_read_A_to_B']}")
    print(f"  genuinely-new: {r['genuinely_new']} (copy A={r['copy_A']} B={r['copy_B']} corpus={r['copy_corpus']})")
    print(f"  >>> MORPH SCORE {r['morph_score']}  verdict: {'PASS' if r['verdict'] else 'PARTIAL'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("morph"); ap.add_argument("A"); ap.add_argument("B")
    ap.add_argument("S", nargs="?", type=int, default=6)
    ap.add_argument("--source-genre", default=None); ap.add_argument("--target-genre", default=None)
    a = ap.parse_args()
    r = morph_metric(a.morph, a.A, a.B, a.S, source_genre=a.source_genre, target_genre=a.target_genre)
    _print(r)
    out = Path(a.morph).with_suffix(".morph_metric.json"); out.write_text(json.dumps(r, indent=2))
    print(f"  -> {out}")


if __name__ == "__main__":
    main()
