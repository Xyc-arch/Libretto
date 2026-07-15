#!/usr/bin/env python3
"""build_cases — reproducible case builder for the anomaly-detection task.

Reads coherent real corpus songs READ-ONLY and writes, to a SEPARATE cases dir (never touching the frozen
corpus), a balanced set of probe cases: half CLEAN (an unmodified copy, ground-truth = no anomaly) and half
ANOMALOUS (a copy with exactly one injected anomaly, ground-truth = bar + kind). The probe must decide which.

    python -m libretto.tasks.anomaly.build_cases --n 20 --seed 1 --out paper_data/anomaly_v1/cases

Balanced by construction: N songs, each yields a clean case AND an anomalous case whose kind rotates across
the 4 injectors, so ~N/2 of each label and the 4 anomaly kinds appear equally.
"""
import argparse
import json
from pathlib import Path

import re

import libretto
from libretto.tasks.anomaly.inject import inject, KINDS, _split, _join

DATA = libretto.data_root()
GRAMMAR = DATA / "grammar"
DEFAULT_OUT = "paper_data/anomaly_v1/cases"
BARS_RANGE = (48, 200)
KIND_LIST = list(KINDS)


def _bars(sid, truth):
    b = truth.get(sid, {}).get("bars")
    return int(b) if str(b).isdigit() else 0


def _excerpt(text, bars, seed):
    """Take a contiguous window of `bars` bars from the interior of the piece, renumbered @1.., keeping the
    header — shorter pieces sharpen localization and reduce the real-chromaticism confound. Pure."""
    import random
    head, blocks = _split(text)
    if len(blocks) <= bars:
        return text
    lo = random.Random(seed).randint(2, len(blocks) - bars - 2)
    win = blocks[lo:lo + bars]
    win = [list(b) for b in win]
    for i, b in enumerate(win, 1):
        b[0] = re.sub(r"^@\d+", f"@{i}", b[0])
    out = [re.sub(r"BARS:\s*\d+", f"BARS: {bars}", head[0])] + head[1:] if head else []
    return _join(out, win)


def build_cases(n=20, seed=1, out=DEFAULT_OUT, excerpt_bars=0):
    """Build 2*n cases (n clean + n anomalous) from n eligible corpus songs. Returns the cases dict. Pure wrt
    the corpus — only reads grammar files, writes copies to `out`. excerpt_bars>0 uses a short window (sharper
    localization, fewer confounding chromatic notes)."""
    import numpy as np
    truth = json.loads((DATA / "answer_key" / "grammar_truth.json").read_text())
    outp = Path(out); outp.mkdir(parents=True, exist_ok=True)
    eligible = sorted(s for s in truth if BARS_RANGE[0] <= _bars(s, truth) <= BARS_RANGE[1]
                      and (GRAMMAR / f"{s}.txt").exists())
    rng = np.random.RandomState(seed)
    if seed > 0:
        eligible = list(eligible); rng.shuffle(eligible)
    cases = {}
    used = 0
    for sid in eligible:
        if used >= n:
            break
        src = (GRAMMAR / f"{sid}.txt").read_text()          # READ-ONLY
        if excerpt_bars:
            src = _excerpt(src, excerpt_bars, seed + used)   # a copy — corpus untouched
        kind = KIND_LIST[used % len(KIND_LIST)]
        anom_text, meta = inject(src, kind, seed=seed)
        if anom_text is None:                                # no suitable site for this kind — skip song
            continue
        # CLEAN case (unmodified copy)
        cc = f"{sid}__clean"
        (outp / f"{cc}.txt").write_text(src)
        cases[cc] = dict(sid=sid, genre=truth[sid].get("genre"), has_anomaly=False, kind="none", bar=None)
        # ANOMALOUS case (one injected anomaly)
        ac = f"{sid}__{kind}"
        (outp / f"{ac}.txt").write_text(anom_text)
        cases[ac] = dict(sid=sid, genre=truth[sid].get("genre"), has_anomaly=True, kind=kind,
                         bar=meta["bar"], voice=meta.get("voice"), change=meta.get("change"))
        used += 1
    (outp / "cases.json").write_text(json.dumps(cases, indent=2))
    return cases


def build_clean_source_cases(n=20, seed=1, out=DEFAULT_OUT, bars=12):
    """Like build_cases but the source is GENERATED theory-clean chorales (clean_source), not real songs — so
    the clean control is genuinely anomaly-free and the false-positive rate is honest. Injects whichever kinds
    have a site in the chorale (out_of_key / wrong_bass / meter_glitch / voice_crossing on whole-note SATB)."""
    from libretto.tasks.anomaly.clean_source import clean_piece, TONICS
    outp = Path(out); outp.mkdir(parents=True, exist_ok=True)
    keys = list(TONICS)
    cases = {}
    used = 0
    attempt = 0
    while used < n and attempt < n * 8:
        key = keys[attempt % len(keys)]
        src = clean_piece(key, bars=bars, seed=seed * 100 + attempt)      # generated clean copy
        attempt += 1
        if src is None:
            continue
        # rotate through the kinds; take the first that injects on this chorale
        order = KIND_LIST[used % len(KIND_LIST):] + KIND_LIST[:used % len(KIND_LIST)]
        anom_text = meta = None
        for kind in order:
            anom_text, meta = inject(src, kind, seed=seed + used)
            if anom_text is not None:
                break
        if anom_text is None:
            continue
        sid = f"clean_{key}_{used:02d}"
        (outp / f"{sid}__clean.txt").write_text(src)
        cases[f"{sid}__clean"] = dict(sid=sid, genre="synthetic_clean", has_anomaly=False, kind="none", bar=None)
        (outp / f"{sid}__{meta['kind']}.txt").write_text(anom_text)
        cases[f"{sid}__{meta['kind']}"] = dict(sid=sid, genre="synthetic_clean", has_anomaly=True,
                                               kind=meta["kind"], bar=meta["bar"], voice=meta.get("voice"),
                                               change=meta.get("change"))
        used += 1
    (outp / "cases.json").write_text(json.dumps(cases, indent=2))
    return cases


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n", type=int, default=20, help="number of songs (-> 2n cases: n clean + n anomalous)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--excerpt-bars", type=int, default=0, help="use a short N-bar window (0 = whole song)")
    ap.add_argument("--source", choices=["corpus", "clean"], default="corpus",
                    help="corpus = real songs (confounded clean control); clean = generated theory-clean chorales")
    a = ap.parse_args()
    if a.source == "clean":
        cases = build_clean_source_cases(n=a.n, seed=a.seed, out=a.out)
    else:
        cases = build_cases(n=a.n, seed=a.seed, out=a.out, excerpt_bars=a.excerpt_bars)
    from collections import Counter
    anom = {k: v for k, v in cases.items() if v["has_anomaly"]}
    print(f"built {len(cases)} cases ({len(anom)} anomalous + {len(cases)-len(anom)} clean) -> {a.out}")
    print("anomaly kinds:", dict(Counter(v["kind"] for v in anom.values())))


if __name__ == "__main__":
    main()
