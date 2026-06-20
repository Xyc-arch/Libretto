#!/usr/bin/env python3
"""refine_loop.py — self-evolving refinement loop for newgen (from-scratch generation).

Same mechanism as the genre self-evolving loop (core.genre_band_check dosage engine). Newgen is from
SCRATCH — there is no source and no held-out answer, so the loop is leakage-free by construction: the
fitness is the newgen gate itself (all structural, all computable from the piece + the frozen corpus).

  generate -> piece_fitness (C1 non-degeneracy + length + copy_risk + genre-band fit + out-of-band axes)
           -> dosage_feedback (mid-band corrections) -> regenerate, <= max_iter rounds, pick best by score.
"""
import io, json, os
from contextlib import redirect_stdout
from pathlib import Path
import numpy as np
import libretto
from libretto.core import Song, metrics_for, copy_risk
from libretto.core import genre_band_check as gbc
from libretto.core import axis_feedback as afb
from . import calibrate as cal

DATA = libretto.data_root()
CANON = json.loads((DATA / "corpus_distribution_314.json").read_text())
AXES = CANON["axes_order"]; COLS = {a: np.array(CANON["axes"][a]["values"], float) for a in AXES}
GC = CANON["genre_conditioned"]; SPLIT = list(GC.keys())
LEN_LO, LEN_HI = 64, 179
COPY_THRESHOLD = 0.30
MAX_ITER_DEFAULT = 3


def fp(path):
    m = metrics_for(Song(path), path)
    return {a: round(float((COLS[a] <= float(m[a])).mean() * 100)) for a in AXES}, m


def genre_aware_extremes(prof, m, genre):
    out = []
    for a in AXES:
        if prof[a] <= 5 or prof[a] >= 95:
            v = float(m[a])
            if genre and a in GC and genre in GC[a] and GC[a][genre]["p25"] <= v <= GC[a][genre]["p75"]:
                continue
            out.append((a, prof[a]))
    return out


def genre_fit(m, genre):
    if not genre:
        return None, []
    inb, out = 0, []
    for ax in SPLIT:
        v = float(m[ax]); b = GC[ax][genre]
        ok = (v >= 11) if ax == "har_distinct_pc" and b["p75"] >= 12 else (b["p25"] <= v <= b["p75"])
        inb += ok
        if not ok:
            # carry the CORRECT direction: below the band -> raise, above -> lower (not always "raise")
            out.append((ax, "increase" if v < b["p25"] else "decrease"))
    return inb, out


def piece_fitness(piece_path, *, genre=None):
    """Structural fitness for one newgen round (no source, no answer -> leakage-free)."""
    prof, m = fp(piece_path)
    bars = len(sorted({e["bar"] for e in Song(piece_path).events}))
    budget = cal.c1_budget(genre); fit_thr = cal.fit_threshold(genre)   # ADAPTIVE, genre-calibrated
    copy_thr = cal.copy_threshold(genre)                                # ADAPTIVE copy gate (real ceiling x1.2)
    exts = genre_aware_extremes(prof, m, genre); c1_pass = len(exts) <= budget
    c2_pass = LEN_LO <= bars <= LEN_HI
    cr = copy_risk(piece_path, vs_corpus=True, threshold=copy_thr); copy_pass = cr["copy_risk"] < copy_thr
    with redirect_stdout(io.StringIO()):
        oob, ext_glob, _ = gbc.check(piece_path, genre=genre if (genre in gbc.genres()) else None)
    fit, fit_out = genre_fit(m, genre)
    fit_ok = (genre is None) or (fit >= fit_thr)
    converged = c1_pass and c2_pass and copy_pass and fit_ok
    c1_pen = max(0, len(exts) - budget) * 40
    c2_pen = 0 if c2_pass else 50
    copy_pen = max(0.0, cr["copy_risk"] - copy_thr) * 300
    fit_pen = 0 if genre is None else max(0, fit_thr - fit) * 15
    score = c1_pen + c2_pen + copy_pen + fit_pen + len(oob) * 2
    return {
        "bars": bars, "c2_pass": c2_pass, "c1_extremes": [(a, p) for a, p in exts], "c1_pass": c1_pass,
        "c1_budget": budget, "fit_threshold": fit_thr, "copy_threshold": copy_thr,
        "copy_risk": cr["copy_risk"], "copy_pass": copy_pass,
        "oob": [(a, round(v, 3), st) for (a, v, st, _p) in oob], "n_oob": len(oob),
        "genre_fit": fit, "genre_fit_out": fit_out, "converged": bool(converged), "score": round(float(score), 1),
    }


def dosage_feedback(fit):
    """Turn one round's structural signals into MUSICIAN-READABLE corrections for the next round."""
    lines = []
    if not fit["c2_pass"]:
        lines.append(f"LENGTH: {fit['bars']} bars; write a full piece within [{LEN_LO},{LEN_HI}] bars.")
    budget = fit.get("c1_budget", 3)
    if not fit.get("c1_pass", len(fit["c1_extremes"]) <= budget):
        names = ", ".join(afb.musical_name(a) for a, _ in fit["c1_extremes"])
        lines.append(f"NON-DEGENERACY: {len(fit['c1_extremes'])} traits are pinned at an extreme ({names}); "
                     f"the genre allows up to {budget} — pull the rest toward the idiomatic middle.")
    for a, v, st in fit["oob"]:
        pct = float((COLS[a] <= v).mean() * 100) if a in COLS else None
        lines.append(afb.explain(a, st, pct=pct))
    if not fit["copy_pass"]:
        lines.append(f"COPY: copy_risk {fit['copy_risk']} >= {fit.get('copy_threshold', COPY_THRESHOLD)} "
                     f"(genre-calibrated); invent fresher material — vary reused cells' pitches.")
    if fit.get("genre_fit_out"):
        # each entry is (axis, direction) — move it the CORRECT way for the target genre band
        gf = "; ".join(afb.explain(a, d) for a, d in fit["genre_fit_out"])
        lines.append(f"GENRE-FIT: move these into the target-genre band — {gf}")
    return lines


def _corrections_block(corrections):
    body = "\n".join(f"  {i+1}. {c}" for i, c in enumerate(corrections))
    return ("\n\n=====================================================================\n"
            "## REVISION FEEDBACK (from a structural band-check of your previous attempt; aim the idiomatic\n"
            "## middle, do NOT overshoot to the opposite extreme; keep musical variety/spread)\n"
            f"{body}\n\nRe-emit the FULL grammar block (header + VOICES + all bars). Grammar only, no prose.\n")


class RefinementLoop:
    """Generator-driven self-evolving loop for newgen (from-scratch, leakage-free).

    Plug any `libretto.generation` Generator (`.generate(prompt, context) -> grammar text`). Each round:
    generate -> piece_fitness -> if converged stop, else append musician-readable dosage_feedback to the
    prompt and regenerate. Returns (best_round_fitness, [all rounds]); pick-best is lowest structural score.
    """

    def __init__(self, generator, max_iter=MAX_ITER_DEFAULT):
        self.generator = generator
        self.max_iter = max_iter

    def run(self, base_prompt, *, genre=None, context=None, workdir=".", label="newgen"):
        workdir = Path(workdir); context = dict(context or {})
        rounds, best, corrections = [], None, []
        for r in range(1, self.max_iter + 1):
            prompt = base_prompt + (_corrections_block(corrections) if corrections else "")
            grammar = self.generator.generate(prompt, context)
            p = workdir / f"{label}_r{r}.txt"; p.write_text(grammar, encoding="utf-8")
            fit = piece_fitness(p, genre=genre); fit["round"] = r; fit["path"] = str(p)
            fit["feedback"] = dosage_feedback(fit)
            rounds.append(fit)
            if best is None or fit["score"] < best["score"]:
                best = fit
            if fit["converged"]:
                break
            corrections = fit["feedback"]
        return best, rounds
