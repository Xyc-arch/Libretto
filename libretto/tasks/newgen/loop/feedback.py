#!/usr/bin/env python3
"""feedback.py — the composer's nontrivial feedback (the design deltas over refine_loop's dosage):

  STEER  (P3)  — a genre classifier on the 39-axis fingerprints says what the draft READS as vs the
                 target, and ranks the axes pulling it wrong (classifier-importance × distance-to-target).
  GUARDRAIL(P1/P2) — flag axes beyond the TARGET GENRE's p5/p95 (genre_conditioned) — extreme *for the
                 genre*, not globally — with direction. (Not push-to-middle; only correct extremes.)
  NOVELTY      — copy_risk gate.

Every flagged axis is translated to a musical action using the axis's own docstring (axes_v3), so the
agent gets "raise blue-note content" not "raise axis_blue_note_content to the 60th pct".
"""
import json
import numpy as np
import libretto
from libretto.core import axes_v3
from libretto.core import copy_risk as copy_risk_fn      # copy_risk is a function, not a module
from libretto.tasks.newgen.refine_loop import fp        # (percentile_profile, raw_metrics) for a piece

DATA = libretto.data_root()
CANON = json.loads((DATA / "corpus_distribution.json").read_text())
AXES = CANON["axes_order"]
GC = CANON["genre_conditioned"]
# per-genre extreme BUDGET, calibrated to the real corpus: how many of the 39 axes a *real* song of the
# genre itself has outside its genre p5/p95 band (median). By construction ~10% of songs sit outside each
# 90% band, so a real song averages ~3.3 extremes — a flat ≤2 gate is stricter than a typical real song of
# most genres, which is why convergence almost never fired. We accept "as idiomatic as a typical real song".
BUDGET = CANON.get("genre_extreme_budget", {})
# per-genre copy gate, calibrated to the real corpus: p90 of how much a REAL song of the genre overlaps
# its nearest OTHER corpus song (leave-one-out). A generated piece under this is at least as novel as 90%
# of real songs of the genre — principled, and genre-aware (some genres have more near-duplicate material).
COPY_BUDGET = CANON.get("genre_copy_budget", {})
# CAUSAL CE weight per axis = |within-song Spearman(dose, AudioBox-CE)| from the perturbation validation
# (EXP_RESULTS_axis_quality_v3): how much pushing that axis to an extreme actually lowers perceived
# enjoyment. Quality-bearing axes (chord_simultaneity .95 … chromaticism .55) weigh far more than stylistic
# ones (register_center .10, offbeat .05). Unvalidated axes get a modest prior (most axes are descriptive).
try:
    CE_WEIGHT = json.loads((DATA / "axis_ce_weights.json").read_text())
except Exception:  # noqa: BLE001
    CE_WEIGHT = {}
W_DEFAULT = 0.3


def causal_weight(axis):
    return float(CE_WEIGHT.get(axis, W_DEFAULT))


def extreme_budget(genre):
    return int(BUDGET.get(genre, {}).get("median", 2))   # CONVERGENCE bar: as idiomatic as a TYPICAL song


def extreme_stop(genre):
    # EARLY-STOP bar (looser than convergence): p75 = the top of the genre's NORMAL range. A piece here is
    # decent/within-idiom, so stop grinding expensive revise rounds to shave the last extreme.
    b = BUDGET.get(genre, {})
    return int(b.get("p75", b.get("median", 3)))


COPY_CAP = 0.55   # "recognizable variation" line (copy_risk.py); above it a piece is a near-copy


def copy_gate(genre):
    # genre p90 = how novel real songs of the genre are vs each other, BUT it's inflated by clean_midi's
    # near-duplicate songs (p90 hits 0.9+ for dup-heavy genres). Cap at the recognizable-variation line so
    # the gate is "as lenient as real songs of the genre, but never permits a near-copy".
    p90 = float(COPY_BUDGET.get(genre, {}).get("p90", 0.35))
    return min(p90, COPY_CAP)
FPS = json.loads((DATA / "corpus_fps.json").read_text())
TRUTH = json.loads((DATA / "answer_key" / "grammar_truth.json").read_text())

# ---- train the genre classifier ONCE on the corpus fingerprints ----
from sklearn.linear_model import LogisticRegression  # noqa: E402
_sids = [s for s in FPS if TRUTH.get(s, {}).get("genre")]
_X = np.array([FPS[s] for s in _sids], float)
_y = np.array([TRUTH[s]["genre"] for s in _sids])
CLF = LogisticRegression(max_iter=2000, class_weight="balanced").fit(_X, _y)
GENRES = list(CLF.classes_)
CENTROID = {g: np.median(_X[_y == g], axis=0) for g in GENRES}
COPY_MAX = 0.35


def _desc(axis):
    fn = axes_v3.REGISTRY.get(axis)
    d = (getattr(fn, "__doc__", "") or "").strip().replace("\n", " ")
    return d.split(";")[0].split("(")[0].strip()[:80] or axis


def classifier_steer(fpvec, genre, k=5):
    """(headline, [ranked musical steer lines], reads_as_target)."""
    p = CLF.predict_proba([fpvec])[0]
    pred = GENRES[int(np.argmax(p))]; prob = float(p.max())
    tgt_prob = float(p[GENRES.index(genre)]) if genre in GENRES else 0.0
    if pred == genre:
        return f"reads as {genre} ({prob:.0%}) ✓", [], True
    head = f"reads as {pred} ({prob:.0%}), NOT {genre} ({tgt_prob:.0%})"
    lines = []
    if genre in GENRES:
        coef = CLF.coef_[GENRES.index(genre)]          # per-axis importance for the target genre
        gap = CENTROID[genre] - np.asarray(fpvec, float)   # +percentiles => raise toward target
        rank = np.argsort(-(np.abs(gap) * np.abs(coef)))   # classifier-weighted distance-to-target
        for i in rank[:k]:
            if abs(gap[i]) >= 10:                        # ≥10 percentiles off
                lines.append(f"{'raise' if gap[i] > 0 else 'lower'} {_desc(AXES[i])}  → toward {genre}")
    return head, lines, False


def guardrail(m, genre):
    """Axes beyond the target genre's p5/p95 band, ranked by PRIORITY = severity × causal CE weight — so
    an axis that is both far out of band AND causally quality-bearing (chord density, harmonic chaos) is
    fixed before one that is out of band but merely stylistic (register, syncopation). Severity = distance
    outside the band / band width."""
    scored = []
    for a in AXES:
        b = GC.get(a, {}).get(genre)
        if not b:
            continue
        v = float(m[a])
        width = max(b["p95"] - b["p5"], 1e-6)
        if v < b["p5"]:
            sev = (b["p5"] - v) / width
            line = f"raise {_desc(a)}  (below {genre}'s plausible range)"
        elif v > b["p95"]:
            sev = (v - b["p95"]) / width
            line = f"lower {_desc(a)}  (above {genre}'s plausible range)"
        else:
            continue
        scored.append((sev * causal_weight(a), line))
    scored.sort(key=lambda t: -t[0])
    return [line for _, line in scored]


def causal_weighted_extremity(m, genre):
    """Idiomaticity-where-it-MATTERS: sum of causal CE weights over the axes out of the genre's band. An
    out-of-band quality axis (chord_simultaneity, w=.95) adds far more than a stylistic one (register, .10).
    Lower = the piece's deviations are on axes that don't hurt perceived quality."""
    tot = 0.0
    for a in AXES:
        b = GC.get(a, {}).get(genre)
        if not b:
            continue
        v = float(m[a])
        if v < b["p5"] or v > b["p95"]:
            tot += causal_weight(a)
    return round(tot, 2)


def compose_feedback(piece_path, genre):
    """(feedback_lines, converged, info). converged = reads as target + within the genre's real-corpus
    extreme BUDGET (as idiomatic as a typical real song of the genre) + novel."""
    prof, m = fp(piece_path)
    fpvec = [prof[a] for a in AXES]
    head, steer, is_target = classifier_steer(fpvec, genre)
    gr = guardrail(m, genre)
    cr = float(copy_risk_fn(str(piece_path)).get("copy_risk", 0.0))
    bud = extreme_budget(genre)
    cgate = copy_gate(genre)
    lines = [f"[GENRE] {head}"]
    lines += [f"  - {s}" for s in steer]
    if gr:
        lines.append(f"[BEYOND {genre} p5/p95] {len(gr)} axes out of band (a typical {genre} song has "
                     f"~{bud}) — fix the WORST first, leave in-band axes alone:")
        lines += [f"  - {g}" for g in gr[:4]]
    lines.append(f"[NOVELTY] copy_risk={cr:.2f} (gate {cgate:.2f})"
                 + (f"  ⚠ too close to a real {genre} song — change the melody/rhythm to vary it" if cr > cgate else ""))
    converged = is_target and len(gr) <= bud and cr <= cgate
    cwx = causal_weighted_extremity(m, genre)   # idiomaticity weighted by causal CE impact (main metric #2)
    info = dict(reads_as=head, is_target=is_target, n_extreme=len(gr), copy_risk=cr,
                budget=bud, budget_stop=extreme_stop(genre), copy_gate=cgate, cw_extremity=cwx)
    return lines, converged, info
