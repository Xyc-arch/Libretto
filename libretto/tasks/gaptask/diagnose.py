#!/usr/bin/env python3
"""diagnose.py — GROUNDED per-case diagnostic for a generated gaptask region.

Given a generated region (+ its visible context, genre, target length, neighbor scaffold, and optionally the
held-out real region), this localizes *what is not good* down to specific BARS and NOTES — never a free-text
guess. Every claim is recomputed from the fingerprint / copy-overlap machinery used by the gate, so an agent
narrating the output cannot invent a problem the metrics don't show.

What it localizes:
  * C1 non-degeneracy — for each genre-aware extreme axis, leave-one-bar-out attribution: which bars, if
    removed, would most move the axis back toward the centre (the bars that "cause" the extreme).
  * C3 / copy      — the single most-overlapping source song, the bar alignment offset, and the exact
                     (bar, onset, pitch) notes that coincide, grouped by generated bar.
  * C2 length      — bars produced vs the gap size.
  * replication    — note overlap with the held-out real region (leak / regurgitation), localized the
                     same way as copy, only when a real region is supplied.

`diagnose()` is leakage-clean except for the explicitly opt-in `real_path` block (mirrors final_grade):
the C1/C2/copy-vs-corpus findings never read the answer.
"""
import io, re
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np

from libretto.core import Song, metrics_for, copy_risk, axis_feedback as afb
from libretto.core.copy_risk import piece_notes, slide_overlap, aligned_overlap, GRAMMAR
from . import refine_loop as rl

AXES = rl.AXES; COLS = rl.COLS


def _split_blocks(text):
    h, b, cur = [], [], None
    for ln in text.splitlines():
        if ln.startswith("@"):
            if cur is not None: b.append(cur)
            cur = [ln]
        elif cur is None: h.append(ln)
        else: cur.append(ln)
    if cur is not None: b.append(cur)
    return h, b


def _emit(header, blocks):
    out = [re.sub(r"BARS:\s*\d+", f"BARS: {len(blocks)}", header[0])] + header[1:]
    for i, blk in enumerate(blocks, 1):
        bb = list(blk); bb[0] = re.sub(r"^@\d+", f"@{i}", bb[0]); out += bb
    return "\n".join(out) + "\n"


def _pct(axis, value):
    return float((COLS[axis] <= value).mean() * 100)


def _axis_pcts(path):
    m = metrics_for(Song(path), path)
    return {a: _pct(a, float(m[a])) for a in AXES}, m


def localize_c1(region_path, extremes, tmp_dir=None):
    """Leave-one-bar-out attribution for each extreme axis. For axis `a` at percentile p (extreme), removing
    bar b recomputes p; |Δtoward-50| ranks the bars most responsible for the extreme. Returns
    {axis: {pct, direction, culprit_bars:[(bar, pct_without_bar, shift_toward_centre)]}}."""
    text = Path(region_path).read_text()
    header, blocks = _split_blocks(text)
    tmp_dir = Path(tmp_dir or Path(region_path).parent)
    tmp = tmp_dir / "_diag_loo.txt"
    base, _ = _axis_pcts(region_path)
    # one recompute per bar (covers all axes at once)
    without = {}
    if len(blocks) > 2:
        for i in range(len(blocks)):
            sub = blocks[:i] + blocks[i + 1:]
            tmp.write_text(_emit(header, sub))
            try:
                without[i], _ = _axis_pcts(tmp)
            except Exception:
                without[i] = None
        tmp.unlink(missing_ok=True)
    out = {}
    for a, pct in extremes:
        direction = "increase" if pct <= 50 else "decrease"      # which way it must move to leave the extreme
        ranked = []
        for i, wo in without.items():
            if wo is None: continue
            # shift toward centre (50) achieved by dropping bar i
            shift = abs(base[a] - 50) - abs(wo[a] - 50)
            ranked.append((i + 1, round(wo[a]), round(shift, 1)))
        ranked = [r for r in ranked if r[2] > 0.5]
        ranked.sort(key=lambda r: -r[2])
        # An axis pinned too HIGH is usually driven by a few bars (removing them helps -> localizable).
        # An axis pinned too LOW (a deficit: too few notes / no variation) is a uniform property of the whole
        # region — no single bar "causes" it, so leave-one-out finds nothing. Say so explicitly.
        scope = "localized" if ranked else "global_deficit"
        out[a] = {
            "musical_name": afb.musical_name(a), "pct": round(pct), "direction": direction,
            "explain": afb.explain(a, direction, pct=pct),
            "scope": scope, "culprit_bars": ranked[:4],
        }
    return out


def _overlap_by_bar(gen_bb, song_bb, offset):
    """Per generated bar: the exact matched (onset, pitch) notes at this alignment."""
    rows = []
    for b in sorted(gen_bb):
        sb = song_bb.get(b + offset)
        if not sb: continue
        shared = sorted(gen_bb[b] & sb)
        if shared:
            rows.append({"gen_bar": b, "src_bar": b + offset, "n": len(shared),
                         "notes": [{"onset": on, "pitch": pi} for on, pi in shared]})
    rows.sort(key=lambda r: -r["n"])
    return rows


def localize_copy(region_path, source_id=None, source_path=None):
    """Localize note reuse against the single binding source song (by id from data/grammar, or an explicit
    path e.g. the held-out real region). Returns the offset + per-bar matched notes (top bars first)."""
    if source_path is None and source_id is not None:
        source_path = GRAMMAR / f"{source_id}.txt"
    if source_path is None or not Path(source_path).exists():
        return None
    gen_bb, _, gen_total = piece_notes(region_path)
    src_bb, _, _ = piece_notes(source_path)
    ov, off = slide_overlap(gen_bb, gen_total, src_bb)
    rows = _overlap_by_bar(gen_bb, src_bb, off)
    return {"source": Path(source_path).stem, "overlap": round(ov, 3), "offset": off,
            "matched_notes": sum(r["n"] for r in rows), "total_notes": gen_total,
            "bars": rows[:6]}


def diagnose(region_path, ctx_path, *, genre, target_bars, neighbor_ids=None, real_path=None):
    """Full grounded diagnosis. Structural (leakage-clean) findings + optional held-out replication block."""
    fit = rl.region_fitness(region_path, ctx_path, genre=genre, target_bars=target_bars,
                            neighbor_ids=neighbor_ids)
    findings = {"bars": fit["bars"], "target_bars": fit["target_bars"], "score": fit["score"],
                "failed": [], "c1": None, "copy": None, "length": None, "replication": None,
                "out_of_band": [(a, afb.musical_name(a), v, st) for a, v, st in fit["oob"]]}

    # C1 non-degeneracy -> bar attribution
    if not fit["c1_pass"]:
        findings["failed"].append("C1_non_degeneracy")
        findings["c1"] = localize_c1(region_path, fit["c1_extremes"])

    # C2 length
    if not fit["c2_pass"]:
        findings["failed"].append("C2_length")
        findings["length"] = {"produced": fit["bars"], "target": fit["target_bars"],
                              "delta": fit["bars"] - fit["target_bars"]}

    # C3 / copy vs the material the generator could see (cited + corpus) -> note attribution
    cr = copy_risk(region_path, cited=neighbor_ids, vs_corpus=True)
    if not cr["pass"]:
        findings["failed"].append("C3_copy")
    if cr["copy_risk"] > 0.0:
        # the binding source = whichever single song attains copy_risk
        src = None
        for key in ("max_cited", "max_corpus"):
            blk = cr.get(key) or {}
            if blk.get("song") and abs(blk.get("overlap", 0) - cr["copy_risk"]) < 1e-6:
                src = blk["song"]; break
        findings["copy"] = {"copy_risk": cr["copy_risk"], "gate": 0.30, "pass": cr["pass"],
                            "detail": localize_copy(region_path, source_id=src) if src else None}

    # held-out replication (opt-in; the only block that reads the answer)
    if real_path is not None:
        gen_bb, _, gtot = piece_notes(region_path)
        rb, _, _ = piece_notes(real_path)
        ov_al = aligned_overlap(gen_bb, gtot, rb, 0)
        ov_sl, off = slide_overlap(gen_bb, gtot, rb)
        repl = ov_sl >= 0.30
        findings["replication"] = {"overlap_aligned": round(ov_al, 3), "overlap_slid": round(ov_sl, 3),
                                   "flag": bool(repl),
                                   "detail": localize_copy(region_path, source_path=real_path) if ov_sl > 0.05 else None}
        if repl: findings["failed"].append("replication")
    return findings
