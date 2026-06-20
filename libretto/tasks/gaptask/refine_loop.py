#!/usr/bin/env python3
"""refine_loop.py — self-evolving refinement loop for the gaptask (LEAKAGE-CLEAN by construction).

Same mechanism as the genre self-evolving loop (libretto.core.genre_band_check / band engine), but the
per-round fitness signal is PURELY STRUCTURAL and is computed from the generated region + the surrounding
CONTEXT + the target band only. It NEVER reads, fingerprints, or compares against the held-out real region.

  generate (blind)  ->  region_fitness(region, context, genre, target_bars, neighbors)  -> dosage_feedback
        ^                                                                                        |
        +-------------------------- regenerate with corrections (<= max_iter rounds) <-----------+

The held-out real region is touched ONLY by final_grade(), which runs AFTER the loop has already picked
its best round — exactly as in single-shot gaptask. The proximity / beat% number is therefore never part
of the loop's feedback; the generator stays blind to the answer throughout.

LEAKAGE GUARANTEE (verify in the wiring): region_fitness() and dosage_feedback() take NO real-region
argument. Only final_grade() has a `real_path` parameter, and it is never called inside the loop.
"""
import json
import os
import io
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np

import libretto
from libretto.core import Song, metrics_for, copy_risk
from libretto.core import genre_band_check as gbc
from libretto.core import axis_feedback as afb

DATA = libretto.data_root()
CANON = json.loads((DATA / "corpus_distribution_314.json").read_text())
AXES = CANON["axes_order"]
COLS = {a: np.array(CANON["axes"][a]["values"], float) for a in AXES}
GC = CANON["genre_conditioned"]
_CORPUS_FP = None

MAX_ITER_DEFAULT = 3            # per the package default; override only if the caller asks
COPY_THRESHOLD = 0.30
OOB_CONVERGE = 6                # "in-band enough" — small, stable out-of-band set


def _corpus_fp():
    global _CORPUS_FP
    if _CORPUS_FP is None:
        _CORPUS_FP = {s: np.array(v, float) for s, v in
                      json.loads((DATA / "corpus_fps.json").read_text()).items()}
    return _CORPUS_FP


def fp(path):
    m = metrics_for(Song(path), path)
    return np.array([round(float((COLS[a] <= float(m[a])).mean() * 100)) for a in AXES], float)


def dist(a, b):
    return float(np.mean(np.abs(a - b)))


def genre_aware_extremes(path, genre):
    """Genre-aware C1: axes at a global extreme (<=5 / >=95 pct), EXCEPT a split axis sitting inside the
    target genre's [p25,p75] (an idiomatic extreme). Mirrors holdout42_measure.ga_ext."""
    m = metrics_for(Song(path), path)
    out = []
    for a in AXES:
        v = float(m[a]); pct = float((COLS[a] <= v).mean() * 100)
        if pct <= 5 or pct >= 95:
            if a in GC and genre in GC[a] and GC[a][genre]["p25"] <= v <= GC[a][genre]["p75"]:
                continue
            out.append((a, round(pct)))
    return out


# ---------------------------------------------------------------------------
#  PER-ROUND FITNESS  — STRUCTURAL ONLY.  NOTE: no `real_path` parameter exists.
# ---------------------------------------------------------------------------
def region_fitness(region_path, ctx_path, *, genre, target_bars, neighbor_ids=None):
    """Leakage-clean structural fitness for one round. Inputs: the generated region, the visible CONTEXT,
    the target genre, the brief's target_bars (the gap SIZE, not its content), and neighbor IDs (scaffold).
    Returns the round's signals + a scalar `score` (lower = better)."""
    s = Song(region_path)
    bars = len(sorted({e["bar"] for e in s.events}))
    rfp, cfp = fp(region_path), fp(ctx_path)
    d_ctx = dist(rfp, cfp)                                   # (b) consistency-with-context

    exts = genre_aware_extremes(region_path, genre)          # (a) non-degeneracy
    c1_pass = len(exts) <= 3
    len_err = abs(bars - target_bars); c2_pass = len_err <= 2  # length vs brief (leakage-clean)

    gtarget = genre if genre in gbc.genres() else None        # (c) in-band via band engine
    with redirect_stdout(io.StringIO()):                      # engine prints a report; keep the loop quiet
        oob, ext_glob, _ = gbc.check(region_path, genre=gtarget)

    cr = copy_risk(region_path, cited=neighbor_ids, vs_corpus=True)   # vs material the generator COULD see
    copy_pass = cr["copy_risk"] < COPY_THRESHOLD                      # NO ref= -> never the held-out answer

    converged = c1_pass and c2_pass and copy_pass and len(oob) <= OOB_CONVERGE
    # GRADED score (lower = closer to passing the gate). Each term is distance-to-gate, not a flat flag,
    # so "pick best" prefers the round nearest a pass rather than one that egregiously fails one criterion:
    c1_pen = max(0, len(exts) - 3) * 40        # how many extremes over the <=3 budget
    c2_pen = 0 if c2_pass else 50
    copy_pen = max(0.0, cr["copy_risk"] - COPY_THRESHOLD) * 300   # how far over the 0.30 copy gate
    score = c1_pen + c2_pen + copy_pen + len(oob) * 2 + len_err * 3 + d_ctx * 0.5
    return {
        "bars": bars, "target_bars": target_bars, "len_err": len_err, "c2_pass": c2_pass,
        "D_ctx": round(d_ctx, 1),
        "c1_extremes": exts, "c1_pass": c1_pass,
        "oob": [(a, round(v, 3), st) for (a, v, st, _p50) in oob], "n_oob": len(oob),
        "glob_extremes": list(ext_glob),
        "copy_risk": cr["copy_risk"], "copy_pass": copy_pass,
        "converged": bool(converged), "score": round(float(score), 1),
    }


def dosage_feedback(fit):
    """Turn one round's structural signals into mid-band dosage corrections for the next round's brief.
    Pure function of `fit` (which carries no held-out info) -> leakage-clean."""
    lines = []
    if not fit["c2_pass"]:
        more = fit["bars"] < fit["target_bars"]
        lines.append(f"LENGTH: you produced {fit['bars']} bars but the gap is ~{fit['target_bars']} (±2). "
                     f"{'Generate MORE bars.' if more else 'Generate FEWER bars — trim the overshoot.'}")
    if len(fit["c1_extremes"]) > 3:
        names = ", ".join(afb.musical_name(a) for a, _ in fit["c1_extremes"])
        lines.append(f"NON-DEGENERACY: {len(fit['c1_extremes'])} traits are pinned at an extreme ({names}); "
                     f"pull them toward the idiomatic middle (do NOT chase the ceiling).")
    for a, v, st in fit["oob"]:
        # st is LOW (raise it) / HIGH (lower it); report WHERE it sits (percentile) + WHICH way to move
        pct = float((COLS[a] <= v).mean() * 100) if a in COLS else None
        lines.append(afb.explain(a, st, pct=pct))
    if not fit["copy_pass"]:
        lines.append(f"COPY: copy_risk {fit['copy_risk']} >= {COPY_THRESHOLD}; invent fresher material — "
                     f"do not reuse neighbor/corpus phrases.")
    return lines


# ---------------------------------------------------------------------------
#  FINAL GRADER  — the ONLY function that may touch the held-out real region.
#  Never called from inside the loop.  Mirrors holdout42_measure's gate + beat%.
# ---------------------------------------------------------------------------
def final_grade(region_path, real_path, ctx_path, *, genre, neighbor_ids=None):
    """Post-loop grade against the held-out REAL region: proximity D_gr + beat% vs chance + the
    holdout42-style gate (C1 genre-aware, C2 length, C3 note/bar copy, replication flag)."""
    rfp = fp(region_path); realfp = fp(real_path); cfp = fp(ctx_path)
    d_gr = dist(rfp, realfp); d_cg = dist(rfp, cfp)
    cfps = _corpus_fp()
    chances = sorted(dist(realfp, cfps[s]) for s in cfps)
    beat = round(sum(1 for d in chances if d > d_gr) / len(chances) * 100)

    gen_bars = len(sorted({e["bar"] for e in Song(region_path).events}))
    real_bars = len(sorted({e["bar"] for e in Song(real_path).events}))
    c1 = len(genre_aware_extremes(region_path, genre)) <= 3
    c2 = abs(gen_bars - real_bars) <= 2
    cr_vs_real = copy_risk(region_path, cited=neighbor_ids, ref=str(real_path), vs_corpus=True)
    answer_overlap = cr_vs_real.get("ref", {}).get("overlap_slid", 0.0)
    c3_note = cr_vs_real["copy_risk"] < COPY_THRESHOLD
    repl = answer_overlap >= 0.30 or (d_gr < 5 and answer_overlap >= 0.20)
    gate_pass = c1 and c2 and c3_note and not repl
    return {
        "D_gr": round(d_gr, 1), "D_cg": round(d_cg, 1), "beat_pct": beat,
        "gen_bars": gen_bars, "real_bars": real_bars,
        "C1": c1, "C2": c2, "C3_note": c3_note, "copy_risk": cr_vs_real["copy_risk"],
        "answer_overlap_slid": round(answer_overlap, 3), "repl_flag": bool(repl),
        "gate_pass": bool(gate_pass),
    }


class RefinementLoop:
    """Drives generate -> structural fitness -> dosage -> regenerate for <= max_iter rounds, picks the
    best round by structural score, and NEVER grades against the answer. Plug any Generator (the
    libretto.generation Generator protocol: .generate(brief, context) -> grammar text)."""

    def __init__(self, generator, max_iter=MAX_ITER_DEFAULT):
        self.generator = generator
        self.max_iter = max_iter

    def run(self, case, workdir, brief_builder):
        """case: {cid, ctx_path, genre, target_bars, neighbor_ids, context}.
        brief_builder(case, corrections) -> the generation prompt for a round."""
        workdir = Path(workdir)
        rounds, best, corrections = [], None, []
        for r in range(1, self.max_iter + 1):
            brief = brief_builder(case, corrections)
            grammar = self.generator.generate(brief, case.get("context", {}))
            rp = workdir / f"{case['cid']}_loop_r{r}.txt"
            rp.write_text(grammar, encoding="utf-8")
            fit = region_fitness(rp, case["ctx_path"], genre=case["genre"],
                                 target_bars=case["target_bars"], neighbor_ids=case.get("neighbor_ids"))
            fit["round"] = r; fit["path"] = str(rp); rounds.append(fit)
            if best is None or fit["score"] < best["score"]:
                best = fit
            if fit["converged"]:
                break
            corrections = dosage_feedback(fit)
        return best, rounds
