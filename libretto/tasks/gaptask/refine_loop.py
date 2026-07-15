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
CANON = json.loads((DATA / "corpus_distribution.json").read_text())
AXES = CANON["axes_order"]
COLS = {a: np.array(CANON["axes"][a]["values"], float) for a in AXES}
GC = CANON["genre_conditioned"]
_CORPUS_FP = None

MAX_ITER_DEFAULT = 3            # per the package default; override only if the caller asks
OOB_CONVERGE = 6                # "in-band enough" — small, stable out-of-band set

# ── Copy / REPRISE gate — CONDITIONED on real-corpus self-copy, not a flat threshold ────────────────────
# The copy concern in gaptask is REPRISE: a fill that just parrots the song's own VISIBLE context. But real
# music reprises too (median ~0.58 of a real region's material recurs in its context), so a flat gate flags
# genuine, real-like fills as "copies". Instead we condition: measure how much REAL regions self-copy their
# own context (region-vs-context overlap under the SAME mask scheme) and set the gate at the p75 of that
# distribution — a fill is a copy only if it reprises MORE than 75% of real regions of its type do. Reprise
# is region-type-dependent (openings recur most), so the gate is conditioned on gap-type. Calibrated over the
# whole corpus @p75, shipped as pkg data, regenerable via calibrate_region_reprise().
REPRISE_DEFAULT = {"start": 0.79, "infill": 0.77, "cont": 0.69}   # corpus-wide real-region reprise p75
REPRISE_FALLBACK = 0.75         # any region type absent from the table
_REPRISE = None


def region_reprise_threshold(region_type=None):
    """Conditioned reprise gate: the max region-vs-own-context overlap a fill may have before it counts as a
    copy = the p75 of REAL regions of this gap-type (region-appropriate; real music reprises this much)."""
    global _REPRISE
    if _REPRISE is None:
        f = DATA / "gaptask_region_reprise_p75.json"
        _REPRISE = json.loads(f.read_text()) if f.exists() else dict(REPRISE_DEFAULT)
    return float(_REPRISE.get(region_type, REPRISE_FALLBACK))


def region_reprise(region_path, ctx_path):
    """Self-copy / reprise of a region = fraction of its material that recurs in its OWN visible context
    (same song, leakage-clean — the context is what the agent could see). Pairwise, not vs-corpus."""
    ov = copy_risk(str(region_path), ref=str(ctx_path), vs_corpus=False)
    return float(ov.get("ref", {}).get("overlap_slid", 0.0))

# Region non-degeneracy budget — genre-conditioned. A short masked region (~15-40 bars) legitimately
# carries more genre-idiomatic extremes than a full piece, so the full-piece budget of 3 is too strict
# (even REAL regions of some genres fail it). Calibrated to real short-region genre-aware extremes @0.85
# quantile; shipped as pkg data and regenerable via calibrate_region_budgets(). Falls back to the
# region-appropriate default for any genre absent from the table (or if the data file is missing).
REGION_BUDGET_DEFAULT = 6
_REGION_BUDGET = None


def region_c1_budget(genre=None):
    """Genre-conditioned region non-degeneracy budget: the max # of genre-aware extremes a short masked
    region may carry before it counts as degenerate. Falls back to REGION_BUDGET_DEFAULT for unknown/None."""
    global _REGION_BUDGET
    if _REGION_BUDGET is None:
        f = DATA / "gaptask_region_c1_budget.json"
        _REGION_BUDGET = json.loads(f.read_text()) if f.exists() else {}
    return int(_REGION_BUDGET.get(genre, REGION_BUDGET_DEFAULT))


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


def calibrate_region_budgets(admit=0.85, bars_range=(48, 200), per_genre=None, out_path=None):
    """Regenerate the genre-conditioned region c1 budget from REAL regions (fully reproducible from the
    frozen core). For every eligible corpus song it cuts the 3 gaptask region types (start=first 20%,
    infill=middle 20%, cont=last 25% — identical to gaptask21_setup / build_cases), counts genre-aware
    extremes in each REAL region, and sets each genre's budget to ceil(quantile@`admit`) of those counts.
    The gate then tolerates exactly the short-region degeneracy that real regions of that genre carry.
    Writes gaptask_region_c1_budget.json (the shipped data) and returns the dict."""
    import math, re, tempfile
    truth = json.loads((DATA / "answer_key" / "grammar_truth.json").read_text())
    grammar = DATA / "grammar"

    def split_blocks(t):
        h, b, cur = [], [], None
        for ln in t.splitlines():
            if ln.startswith("@"):
                if cur is not None: b.append(cur)
                cur = [ln]
            elif cur is None: h.append(ln)
            else: cur.append(ln)
        if cur is not None: b.append(cur)
        return h, b

    def write_g(head, groups, path):
        blocks = [x for g in groups for x in g]
        out = [re.sub(r"BARS:\s*\d+", f"BARS: {len(blocks)}", head[0])]
        out += [ln for ln in head[1:] if ln.startswith("VOICES:")]
        for i, blk in enumerate(blocks, 1):
            bb = list(blk); bb[0] = re.sub(r"^@\d+", f"@{i}", bb[0]); out.extend(bb)
        Path(path).write_text("\n".join(out) + "\n", encoding="utf-8")

    def bars_of(sid):
        b = truth[sid].get("bars"); return int(b) if str(b).isdigit() else 0

    lo, hi = bars_range
    by_g = {}
    for sid, v in sorted(truth.items()):
        if lo <= bars_of(sid) <= hi:
            by_g.setdefault(v.get("genre"), []).append(sid)

    counts, tmp = {}, Path(tempfile.mkdtemp(prefix="region_cal_"))
    for g, sids in sorted(by_g.items()):
        if not g:
            continue
        if per_genre:
            sids = sids[:per_genre]
        cs = []
        for sid in sids:
            head, blocks = split_blocks((grammar / f"{sid}.txt").read_text(encoding="utf-8"))
            N = len(blocks)
            if N < 5:
                continue
            for t, gap in (("start",  blocks[0:round(.20 * N)]),
                           ("infill", blocks[round(.40 * N):round(.60 * N)]),
                           ("cont",   blocks[round(.75 * N):N])):
                if not gap:
                    continue
                rp = tmp / f"{sid}_{t}.txt"; write_g(head, [gap], rp)
                cs.append(len(genre_aware_extremes(rp, g)))
        if cs:
            counts[g] = int(math.ceil(float(np.quantile(cs, admit))))
    out = Path(out_path) if out_path else (DATA / "gaptask_region_c1_budget.json")
    out.write_text(json.dumps(dict(sorted(counts.items())), indent=1))
    global _REGION_BUDGET
    _REGION_BUDGET = counts
    return counts


def calibrate_region_reprise(admit=0.75, bars_range=(48, 200), sample_every=1, out_path=None):
    """Regenerate the region-type-conditioned REPRISE gate from REAL regions (reproducible from the frozen
    core). For every eligible corpus song it cuts the 3 gaptask region types (start=first 20%, infill=middle
    20%, cont=last 25%) AND their visible context (start=post, infill=pre+post, cont=pre), measures each real
    region's reprise = region-vs-own-context overlap (pairwise, leakage-clean), and sets each gap-type's gate
    to the `admit` quantile (p75) of those overlaps. The gate then flags a fill only if it reprises MORE than
    real regions of that type do. Writes gaptask_region_reprise_p75.json and returns the dict."""
    import re as _re, tempfile
    truth = json.loads((DATA / "answer_key" / "grammar_truth.json").read_text())
    grammar = DATA / "grammar"

    def split_blocks(t):
        h, b, cur = [], [], None
        for ln in t.splitlines():
            if ln.startswith("@"):
                if cur is not None: b.append(cur)
                cur = [ln]
            elif cur is None: h.append(ln)
            else: cur.append(ln)
        if cur is not None: b.append(cur)
        return h, b

    def write_g(head, groups, path):
        blocks = [x for g in groups for x in g]
        out = [_re.sub(r"BARS:\s*\d+", f"BARS: {len(blocks)}", head[0])]
        out += [ln for ln in head[1:] if ln.startswith("VOICES:")]
        for i, blk in enumerate(blocks, 1):
            bb = list(blk); bb[0] = _re.sub(r"^@\d+", f"@{i}", bb[0]); out.extend(bb)
        Path(path).write_text("\n".join(out) + "\n", encoding="utf-8")

    def bars_of(sid):
        b = truth[sid].get("bars"); return int(b) if str(b).isdigit() else 0

    lo, hi = bars_range
    sids = [s for s, v in sorted(truth.items()) if lo <= bars_of(s) <= hi][::max(1, sample_every)]
    by_t, tmp = {"start": [], "infill": [], "cont": []}, Path(tempfile.mkdtemp(prefix="reprise_cal_"))
    for sid in sids:
        try:
            head, blocks = split_blocks((grammar / f"{sid}.txt").read_text(encoding="utf-8"))
            N = len(blocks)
            if N < 5:
                continue
            segs = {"start":  (blocks[0:round(.20 * N)], blocks[round(.20 * N):N]),
                    "infill": (blocks[round(.40 * N):round(.60 * N)],
                               blocks[0:round(.40 * N)] + blocks[round(.60 * N):N]),
                    "cont":   (blocks[round(.75 * N):N], blocks[0:round(.75 * N)])}
            for t, (gap, ctx) in segs.items():
                if not gap or not ctx:
                    continue
                rp = tmp / f"{sid}_{t}_r.txt"; cp = tmp / f"{sid}_{t}_c.txt"
                write_g(head, [gap], rp); write_g(head, [ctx], cp)
                by_t[t].append(region_reprise(rp, cp))
        except Exception:  # noqa: BLE001 — skip an unparseable song
            continue
    thr = {t: round(float(np.quantile(v, admit)), 3) for t, v in by_t.items() if v}
    out = Path(out_path) if out_path else (DATA / "gaptask_region_reprise_p75.json")
    out.write_text(json.dumps(dict(sorted(thr.items())), indent=1))
    global _REPRISE
    _REPRISE = thr
    return thr


# ---------------------------------------------------------------------------
#  PER-ROUND FITNESS  — STRUCTURAL ONLY.  NOTE: no `real_path` parameter exists.
# ---------------------------------------------------------------------------
def region_fitness(region_path, ctx_path, *, genre, target_bars, neighbor_ids=None, region_type=None):
    """Leakage-clean structural fitness for one round. Inputs: the generated region, the visible CONTEXT,
    the target genre, the brief's target_bars (the gap SIZE, not its content), neighbor IDs (scaffold), and
    the gap-type (start/infill/cont — conditions the reprise gate). Returns the round's signals + a scalar
    `score` (lower = better)."""
    s = Song(region_path)
    bars = len(sorted({e["bar"] for e in s.events}))
    rfp, cfp = fp(region_path), fp(ctx_path)
    d_ctx = dist(rfp, cfp)                                   # (b) consistency-with-context

    exts = genre_aware_extremes(region_path, genre)          # (a) non-degeneracy
    budget = region_c1_budget(genre)                          # genre-conditioned, region-appropriate
    c1_pass = len(exts) <= budget
    len_err = abs(bars - target_bars); c2_pass = len_err <= 2  # length vs brief (leakage-clean)

    gtarget = genre if genre in gbc.genres() else None        # (c) in-band via band engine
    with redirect_stdout(io.StringIO()):                      # engine prints a report; keep the loop quiet
        oob, ext_glob, _ = gbc.check(region_path, genre=gtarget)

    # COPY = REPRISE, conditioned on real self-copy. How much the fill parrots its OWN visible context, gated
    # at the p75 of REAL regions of this gap-type (a fill is a copy only if it reprises MORE than real music
    # does). Leakage-clean: vs the visible context, NO ref= to the held-out answer.
    reprise = region_reprise(region_path, ctx_path)
    rthr = region_reprise_threshold(region_type)
    copy_pass = reprise <= rthr
    plag_vs_corpus = float(copy_risk(region_path, cited=neighbor_ids,
                                     vs_corpus=True).get("copy_risk", 0.0))  # secondary cross-song diagnostic

    converged = c1_pass and c2_pass and copy_pass and len(oob) <= OOB_CONVERGE
    # GRADED score (lower = closer to passing the gate). Each term is distance-to-gate, not a flat flag,
    # so "pick best" prefers the round nearest a pass rather than one that egregiously fails one criterion:
    c1_pen = max(0, len(exts) - budget) * 40   # how many extremes over the genre-conditioned budget
    c2_pen = 0 if c2_pass else 50
    copy_pen = max(0.0, reprise - rthr) * 300   # how far over the conditioned reprise p75
    score = c1_pen + c2_pen + copy_pen + len(oob) * 2 + len_err * 3 + d_ctx * 0.5
    return {
        "bars": bars, "target_bars": target_bars, "len_err": len_err, "c2_pass": c2_pass,
        "D_ctx": round(d_ctx, 1),
        "c1_extremes": exts, "c1_pass": c1_pass, "c1_budget": budget,
        "oob": [(a, round(v, 3), st) for (a, v, st, _p50) in oob], "n_oob": len(oob),
        "glob_extremes": list(ext_glob),
        "copy_risk": round(reprise, 3), "copy_pass": copy_pass, "reprise": round(reprise, 3),
        "reprise_thr": round(rthr, 3), "plag_vs_corpus": round(plag_vs_corpus, 3),
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
    if len(fit["c1_extremes"]) > fit.get("c1_budget", REGION_BUDGET_DEFAULT):
        names = ", ".join(afb.musical_name(a) for a, _ in fit["c1_extremes"])
        lines.append(f"NON-DEGENERACY: {len(fit['c1_extremes'])} traits are pinned at an extreme ({names}); "
                     f"pull them toward the idiomatic middle (do NOT chase the ceiling).")
    for a, v, st in fit["oob"]:
        # st is LOW (raise it) / HIGH (lower it); report WHERE it sits (percentile) + WHICH way to move
        pct = float((COLS[a] <= v).mean() * 100) if a in COLS else None
        lines.append(afb.explain(a, st, pct=pct))
    if not fit["copy_pass"]:
        lines.append(f"REPRISE: your fill reuses {fit.get('reprise', fit['copy_risk']):.2f} of the visible "
                     f"context (over the {fit.get('reprise_thr', 0.75):.2f} bar real regions sit under); invent "
                     f"fresher material — do not parrot the surrounding bars.")
    return lines


# ---------------------------------------------------------------------------
#  FINAL GRADER  — the ONLY function that may touch the held-out real region.
#  Never called from inside the loop.  Mirrors holdout42_measure's gate + beat%.
# ---------------------------------------------------------------------------
def final_grade(region_path, real_path, ctx_path, *, genre, neighbor_ids=None, region_type=None):
    """Post-loop grade against the held-out REAL region: proximity D_gr + beat% vs chance + the gate
    (C1 genre-aware non-degeneracy, C2 length, C3 conditioned reprise-vs-context, replication-vs-answer flag)."""
    rfp = fp(region_path); realfp = fp(real_path); cfp = fp(ctx_path)
    d_gr = dist(rfp, realfp); d_cg = dist(rfp, cfp)
    cfps = _corpus_fp()
    chances = sorted(dist(realfp, cfps[s]) for s in cfps)
    beat = round(sum(1 for d in chances if d > d_gr) / len(chances) * 100)

    gen_bars = len(sorted({e["bar"] for e in Song(region_path).events}))
    real_bars = len(sorted({e["bar"] for e in Song(real_path).events}))
    c1 = len(genre_aware_extremes(region_path, genre)) <= region_c1_budget(genre)
    c2 = abs(gen_bars - real_bars) <= 2
    # C3 = CONDITIONED reprise gate: reuse of the VISIBLE context, gated at the real-region p75 for this
    # gap-type (leakage-clean, matches the loop). Separately, a replication FLAG vs the held-out answer.
    reprise = region_reprise(region_path, ctx_path)
    rthr = region_reprise_threshold(region_type)
    c3_note = reprise <= rthr
    cr_vs_real = copy_risk(region_path, cited=neighbor_ids, ref=str(real_path), vs_corpus=True)
    answer_overlap = cr_vs_real.get("ref", {}).get("overlap_slid", 0.0)
    repl = answer_overlap >= 0.30 or (d_gr < 5 and answer_overlap >= 0.20)
    gate_pass = c1 and c2 and c3_note and not repl
    return {
        "D_gr": round(d_gr, 1), "D_cg": round(d_cg, 1), "beat_pct": beat,
        "gen_bars": gen_bars, "real_bars": real_bars,
        "C1": c1, "C2": c2, "C3_reprise": c3_note, "reprise": round(reprise, 3), "reprise_thr": round(rthr, 3),
        "copy_risk": round(reprise, 3), "plag_vs_corpus": round(float(cr_vs_real["copy_risk"]), 3),
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
                                 target_bars=case["target_bars"], neighbor_ids=case.get("neighbor_ids"),
                                 region_type=case.get("type"))
            fit["round"] = r; fit["path"] = str(rp); rounds.append(fit)
            if best is None or fit["score"] < best["score"]:
                best = fit
            if fit["converged"]:
                break
            corrections = dosage_feedback(fit)
        return best, rounds
