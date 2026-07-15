#!/usr/bin/env python3
"""build_cases — pkg-native, reproducible gaptask case builder.

Constructs a genre-BALANCED set of held-out region-infill cases from the frozen corpus: for each of the 11
genres and 3 gap-types (start / infill / continuation) it selects one song, masks a region, and writes the
visible context + the held-out real region + k=3 neighbor scaffolds. Every variant batch is EXACTLY one song
per genre (11 songs), so a parallel 11-way run is always genre-balanced. Fully reproducible from the frozen
core (grammar + answer key + corpus distribution); `--seed>0` draws a fresh balanced sample.

    python -m libretto.tasks.gaptask.build_cases --seed 1 --out paper_data/gaptask_v3/cases

Region cut (identical to calibrate_region_budgets / calibrate_region_reprise):
  start  = first 20% masked, context = the rest
  infill = middle 20% masked, context = pre + post
  cont   = last 25% masked,  context = the lead-in
"""
import argparse
import json
import re
from collections import Counter
from pathlib import Path

import numpy as np

import libretto
from libretto.core import metrics_for, Song   # 39 axis_* fingerprint metrics (NOT metric_discovery's raw keys)

DATA = libretto.data_root()
GRAMMAR = DATA / "grammar"
GENRES = ["pop_rock", "funk_soul_rnb", "electronic_dance", "jazz", "folk_country", "classical",
          "metal", "hiphop_rap", "reggae_ska", "latin", "blues_gospel"]
VARIANTS = ["start", "infill", "cont"]
K = 3
BARS_RANGE = (48, 200)
DEFAULT_OUT = "paper_data/gaptask_v3/cases"


def _split_blocks(t):
    h, b, cur = [], [], None
    for ln in t.splitlines():
        if ln.startswith("@"):
            if cur is not None:
                b.append(cur)
            cur = [ln]
        elif cur is None:
            h.append(ln)
        else:
            cur.append(ln)
    if cur is not None:
        b.append(cur)
    return h, b


def _write_g(head, groups, path):
    blocks = [x for g in groups for x in g]
    out = [re.sub(r"BARS:\s*\d+", f"BARS: {len(blocks)}", head[0])]
    out += [ln for ln in head[1:] if ln.startswith("VOICES:")]
    for i, blk in enumerate(blocks, 1):
        bb = list(blk); bb[0] = re.sub(r"^@\d+", f"@{i}", bb[0]); out.extend(bb)
    Path(path).write_text("\n".join(out) + "\n", encoding="utf-8")


def build_cases(seed=0, out=DEFAULT_OUT):
    """Build a genre-balanced gaptask case set and return the cases dict. seed=0 = deterministic first-N per
    genre; seed>0 = shuffle each genre's eligible pool for a fresh balanced draw. Writes ctx/real/pre/post
    grammar files + cases.json under `out`. Raises if any genre has too few eligible songs (never emits an
    unbalanced batch)."""
    truth = json.loads((DATA / "answer_key" / "grammar_truth.json").read_text())
    canon = json.loads((DATA / "corpus_distribution.json").read_text())
    axes = canon["axes_order"]
    cols = {a: np.array(canon["axes"][a]["values"], float) for a in axes}
    cfp_all = {s: np.array(v, float) for s, v in json.loads((DATA / "corpus_fps.json").read_text()).items()}
    outp = Path(out); outp.mkdir(parents=True, exist_ok=True)

    def fp(p):
        m = metrics_for(Song(p), p)
        return np.array([round(float((cols[a] <= float(m[a])).mean() * 100)) for a in axes], float)

    def dist(a, b):
        return float(np.mean(np.abs(a - b)))

    def neighbors(ctx_path, sid):
        cfp = fp(ctx_path)
        d = sorted(((dist(cfp, cfp_all[s]), s) for s in cfp_all if s != sid))[:K]
        cen = np.mean([cfp_all[s] for _, s in d], axis=0)
        sal = sorted(range(len(axes)), key=lambda i: abs(cen[i] - 50), reverse=True)[:6]
        return ([(s, round(dd, 1)) for dd, s in d],
                ", ".join(f"{axes[i].split('_', 1)[1]}={int(cen[i])}" for i in sal))

    def bars_of(sid):
        b = truth[sid].get("bars"); return int(b) if str(b).isdigit() else 0

    # ALWAYS BALANCED: len(VARIANTS) distinct songs per genre, one per variant → every variant batch is
    # exactly len(GENRES) songs, one per genre. Abort (not truncate) if a genre is too thin.
    lo, hi = BARS_RANGE
    by_g = {}
    for sid, v in sorted(truth.items()):
        if lo <= bars_of(sid) <= hi:
            by_g.setdefault(v["genre"], []).append(sid)
    short = {g: len(by_g.get(g, [])) for g in GENRES if len(by_g.get(g, [])) < len(VARIANTS)}
    if short:
        raise ValueError(f"cannot build a balanced batch — genres with <{len(VARIANTS)} eligible songs: {short}")
    rng = np.random.RandomState(seed)
    assign = {v: [] for v in VARIANTS}
    for g in GENRES:
        pool = list(by_g[g])
        if seed > 0:
            rng.shuffle(pool)                 # seed=0 keeps the deterministic first-N picks
        for var, sid in zip(VARIANTS, pool[:len(VARIANTS)]):
            assign[var].append(sid)

    cases = {}
    for t, sids in assign.items():
        for sid in sids:
            head, blocks = _split_blocks((GRAMMAR / f"{sid}.txt").read_text()); n = len(blocks)
            if t == "cont":
                pre = blocks[0:round(.75 * n)]; gap = blocks[round(.75 * n):n]; post = None; ctxg = [pre]
            elif t == "infill":
                pre = blocks[0:round(.40 * n)]; gap = blocks[round(.40 * n):round(.60 * n)]
                post = blocks[round(.60 * n):n]; ctxg = [pre, post]
            else:
                pre = None; gap = blocks[0:round(.20 * n)]; post = blocks[round(.20 * n):n]; ctxg = [post]
            cid = f"{sid}_{t}"
            _write_g(head, ctxg, outp / f"{cid}_ctx.txt"); _write_g(head, [gap], outp / f"{cid}_real.txt")
            if pre is not None:
                _write_g(head, [pre], outp / f"{cid}_pre.txt")
            if post is not None:
                _write_g(head, [post], outp / f"{cid}_post.txt")
            ngh, tend = neighbors(outp / f"{cid}_ctx.txt", sid)
            cases[cid] = dict(sid=sid, type=t, genre=truth[sid]["genre"], target_bars=len(gap),
                              ctx=f"{cid}_ctx.txt", real=f"{cid}_real.txt",
                              pre=(f"{cid}_pre.txt" if pre is not None else None),
                              post=(f"{cid}_post.txt" if post is not None else None),
                              neighbors=ngh, tend=tend, hdr=head[0])
    (outp / "cases.json").write_text(json.dumps(cases, indent=2))
    # BALANCE GUARANTEE
    for var in VARIANTS:
        gs = [c["genre"] for c in cases.values() if c["type"] == var]
        assert sorted(gs) == sorted(GENRES), f"UNBALANCED {var} batch: {Counter(gs)}"
    return cases


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seed", type=int, default=0,
                    help="0 = deterministic first-N per genre; >0 = fresh balanced shuffle")
    ap.add_argument("--out", default=DEFAULT_OUT,
                    help="output cases dir (point a new seed at a scratch dir to avoid clobbering the canonical set)")
    a = ap.parse_args()
    cases = build_cases(seed=a.seed, out=a.out)
    print(f"built {len(cases)} cases across {len(GENRES)} genres x {len(VARIANTS)} variants (seed {a.seed}) -> {a.out}")
    print("per variant:", dict(Counter(c["type"] for c in cases.values())), "-> each batch genre-balanced (11/11) OK")
    tb = [c["target_bars"] for c in cases.values()]
    print(f"target_bars range: {min(tb)} - {max(tb)}")


if __name__ == "__main__":
    main()
