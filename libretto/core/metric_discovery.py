#!/usr/bin/env python3
"""
metric_discovery.py — discover a DESCRIPTIVE statistical coordinate system for songs.

Purely descriptive: it locates a song in statistical space (a profile of percentiles across
diverse, well-distributed token-derived axes). It is NOT a quality measure — there is no
"good music" target anywhere. High/low percentile = atypical/typical position, not better/worse.

Pipeline:
  1. ~34 candidate metrics, all derived from the grammar tokens (pitch/onset/duration/voice).
  2. Compute across the 59 real songs (song_0014, generated, excluded); characterize each
     distribution (mean, sd, min, max, skew, kurtosis, bimodality, modal share -> SHAPE).
  3. Score discriminating power: reject DEGENERATE metrics (all songs pile at one value).
  4. Score the SET by diversity: Pearson correlation matrix; greedily prune redundant
     (|r|>=0.80) metrics so each retained axis is ~independent.
  5. (refinement notes are emitted for rejected/redundant axes.)
Output: surviving set + shapes, correlation matrix, 3-4 song fingerprints, and the
song_0014 validation (where its fingerprint sits at the extreme of the real-song axes).
"""
import json
import math
import re
from collections import Counter, defaultdict
import os
from pathlib import Path

import numpy as np

from .understanding_probe import Song

SCRIPT_DIR = Path(os.environ.get("LIBRETTO_DATA") or (Path(__file__).resolve().parent.parent / "data"))
GRAMMAR_DIR = SCRIPT_DIR / "grammar"
ANSWER_KEY = SCRIPT_DIR / "answer_key" / "grammar_truth.json"
OUT = SCRIPT_DIR / "metric_system_report.md"
GENERATED = "song_0014"
CORR_THRESH = 0.75   # |Pearson r| at/above this = redundant (same axis measured twice)
DEGEN_MODAL_SHARE = 0.55     # >this fraction of songs in one 12-bin histogram bin => degenerate
FINGERPRINT_SONGS = ["song_0047", "song_0009", "song_0016", "song_0006"]  # DancingQueen, Stairway, SuperFreak, HotelCalifornia

PC_MAJOR = (0, 2, 4, 5, 7, 9, 11)


# --------------------------------------------------------------------------- #
def read_grid_counts(path):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    default_trip = bool(re.search(r"GRID:\s*\d+t\b", lines[0]))
    trip = binv = 0
    for ln in lines:
        if ln.startswith("@"):
            m = re.search(r"\(grid:(\d+)(t?)\)", ln)
            if m:
                trip += 1 if m.group(2) else 0
                binv += 0 if m.group(2) else 1
            else:
                trip += 1 if default_trip else 0
                binv += 0 if default_trip else 1
    return trip, binv


def entropy(counts):
    tot = sum(counts)
    if tot <= 0:
        return 0.0
    ps = [c / tot for c in counts if c > 0]
    h = -sum(p * math.log2(p) for p in ps)
    return h / math.log2(len(ps)) if len(ps) > 1 else 0.0


def weighted_pcs(song, bar):
    w = defaultdict(float)
    for e in song.events:
        if e["bar"] == bar:
            w[e["pc"]] += e["dur"]
    return w


def prom(w, frac=0.30):
    if not w:
        return frozenset()
    mx = max(w.values())
    return frozenset(pc for pc, x in w.items() if x >= frac * mx)


def bass_melody(song):
    avg = {}
    chord = {}
    for v in song.voices:
        evs = song.voice_events(v)
        if not evs:
            continue
        ons = {e["abs"] for e in evs}
        avg[v] = sum(e["midi"] for e in evs) / len(evs)
        chord[v] = len(evs) / max(1, len(ons))
    if not avg:
        return None, None
    bass = min(avg, key=avg.get)
    mono = [v for v in avg if chord[v] < 1.4 and len({e["abs"] for e in song.voice_events(v)}) >= 8]
    mel = max(mono or list(avg), key=avg.get)
    return bass, mel


def ssm(song):
    bars = sorted({e["bar"] for e in song.events})
    sets = {b: song.bar_event_set(b) for b in bars}
    n = len(bars)
    S = np.ones((n, n))
    for i in range(n):
        ai = sets[bars[i]]
        for j in range(i + 1, n):
            bj = sets[bars[j]]
            u = ai | bj
            s = (len(ai & bj) / len(u)) if u else 1.0
            S[i, j] = S[j, i] = s
    return S, bars, sets


def metrics_for(song, path, base_only=False):
    M = {}
    evs = song.events
    if not evs:
        return None
    bars = sorted({e["bar"] for e in evs})
    nb = len(bars)
    bar_ql = song.bar_ql
    beats = max(1, round(bar_ql))
    onsets = sorted({(e["voice"], e["abs"]) for e in evs})
    n_on = len(onsets)
    durs = np.array([e["dur"] for e in evs], float)
    bass, mel = bass_melody(song)

    # ---- RHYTHM ----
    off = sum(1 for v, ab in onsets if ((ab % bar_ql) % 1.0) > 1e-6)
    M["rhy_syncopation_rate"] = off / n_on
    M["rhy_onset_density_per_bar"] = n_on / nb
    trip, binv = read_grid_counts(path)
    M["rhy_triplet_share"] = trip / max(1, trip + binv)
    # within-bar onset-position entropy (quantized to 1/4 beat)
    pos = Counter(round((e["abs"] % bar_ql) / 0.25) for e in evs)
    M["rhy_onset_pos_entropy"] = entropy(list(pos.values()))
    M["rhy_dur_cv"] = float(durs.std() / durs.mean()) if durs.mean() else 0.0
    M["rhy_mean_dur_beats"] = float(durs.mean())
    perbar = Counter(e["bar"] for e in evs)
    pbv = np.array([perbar[b] for b in bars], float)
    M["rhy_density_variability"] = float(pbv.std() / pbv.mean()) if pbv.mean() else 0.0

    # ---- HARMONY (pitch-class grounded) ----
    pcw = defaultdict(float)
    for e in evs:
        pcw[e["pc"]] += e["dur"]
    tot = sum(pcw.values())
    best = max((sum(pcw[(r + i) % 12] for i in PC_MAJOR) for r in range(12)), default=0)
    M["har_chromaticism"] = 1 - best / tot if tot else 0.0
    M["har_distinct_pc"] = float(len([1 for v in pcw.values() if v > 0]))
    M["har_pc_entropy"] = entropy(list(pcw.values()))
    # chord-change rate over half-bars
    halves = []
    for b in bars:
        for h in (0, 1):
            w = defaultdict(float)
            for e in evs:
                if e["bar"] == b and (e["onb"] < bar_ql / 2) == (h == 0):
                    w[e["pc"]] += e["dur"]
            halves.append(prom(w))
    changes = sum(1 for a, c in zip(halves, halves[1:]) if a and c and a != c)
    M["har_chord_change_rate"] = changes / max(1, len(halves) - 1)
    M["har_vocab_density"] = len(set(h for h in halves if h)) / nb
    # bass root motion
    if bass:
        rt = []
        by = defaultdict(list)
        for e in song.voice_events(bass):
            by[e["bar"]].append(e["midi"])
        for b in sorted(by):
            rt.append(min(by[b]) % 12)
        trans = [(c - a) % 12 for a, c in zip(rt, rt[1:])]
        M["har_root_motion_entropy"] = entropy(list(Counter(trans).values())) if trans else 0.0
        M["har_fourth_motion_rate"] = (sum(1 for t in trans if t == 5) / len(trans)) if trans else 0.0
    else:
        M["har_root_motion_entropy"] = 0.0
        M["har_fourth_motion_rate"] = 0.0
    # sonority RATES (continuous) + boolean "ever" (degenerate demos)
    dom7 = dim = aug = 0
    ever_dom = ever_dim = 0
    for b in bars:
        pcs = prom(weighted_pcs(song, b))
        bd = bdi = 0
        for r in pcs:
            if {r, (r + 4) % 12, (r + 7) % 12, (r + 10) % 12} <= pcs:
                bd = 1
            if {r, (r + 3) % 12, (r + 6) % 12} <= pcs:
                bdi = 1
            if {r, (r + 4) % 12, (r + 8) % 12} <= pcs:
                aug += 1
        dom7 += bd; dim += bdi
        ever_dom = ever_dom or bd; ever_dim = ever_dim or bdi
    M["har_dom7_rate"] = dom7 / nb
    M["har_dimaug_rate"] = (dim + min(aug, nb)) / nb
    M["har_has_dom7_ANY"] = float(ever_dom)        # degeneracy demo (expected ~always 1)
    M["har_has_dim_ANY"] = float(ever_dim)         # degeneracy demo

    # ---- MELODY ----
    allmidi = [e["midi"] for e in evs]
    M["mel_pitch_range"] = float(max(allmidi) - min(allmidi))
    if mel:
        ln = song.line(mel)
        seq = [ln[t] for t in sorted(ln)]
        iv = [b - a for a, b in zip(seq, seq[1:])]
        moves = [d for d in iv if d != 0]
        M["mel_step_ratio"] = (sum(1 for d in moves if abs(d) <= 2) / len(moves)) if moves else 0.0
        M["mel_mean_abs_interval"] = float(np.mean([abs(d) for d in moves])) if moves else 0.0
        M["mel_interval_entropy"] = entropy(list(Counter(min(abs(d), 12) for d in moves).values())) if moves else 0.0
        M["mel_up_ratio"] = (sum(1 for d in moves if d > 0) / len(moves)) if moves else 0.5
        ms = [e["midi"] for e in song.voice_events(mel)]
        M["mel_voice_range"] = float(max(ms) - min(ms)) if ms else 0.0
    else:
        for k in ("mel_step_ratio", "mel_mean_abs_interval", "mel_interval_entropy", "mel_up_ratio", "mel_voice_range"):
            M[k] = 0.0

    # ---- TEXTURE / VOICING ----
    M["tex_voice_count"] = float(len([v for v in song.voices if song.voice_events(v)]))
    M["tex_mean_simultaneity"] = len(evs) / n_on
    widths = []
    byvt = defaultdict(list)
    for e in evs:
        byvt[(e["voice"], e["abs"])].append(e["midi"])
    for ms in byvt.values():
        if len(ms) >= 2:
            widths.append(max(ms) - min(ms))
    M["tex_max_chord_width"] = float(max(widths)) if widths else 0.0
    M["tex_active_voice_density"] = float(np.mean([len({e["voice"] for e in evs if e["bar"] == b}) for b in bars]))
    # doubling ratio: frac of voice pairs that move in unison/octave (>=12 shared onsets, >=90% same pc)
    lines = {v: song.line(v) for v in song.voices}
    vs = [v for v in song.voices if lines[v]]
    pairs = doub = 0
    for i in range(len(vs)):
        for j in range(i + 1, len(vs)):
            sh = set(lines[vs[i]]) & set(lines[vs[j]])
            if len(sh) >= 12:
                pairs += 1
                same = sum(1 for t in sh if (lines[vs[i]][t] - lines[vs[j]][t]) % 12 == 0)
                if same / len(sh) >= 0.9:
                    doub += 1
    M["tex_doubling_ratio"] = doub / pairs if pairs else 0.0

    # ---- FORM / STRUCTURE (from SSM) ----
    S, sbars, sets = ssm(song)
    n = len(sbars)
    if n >= 2:
        iu = np.triu_indices(n, 1)
        M["form_self_similarity"] = float(S[iu].mean())
        adj = np.array([S[i, i + 1] for i in range(n - 1)])
        M["form_novelty_rate"] = float((1 - adj).mean())
    else:
        M["form_self_similarity"] = 1.0
        M["form_novelty_rate"] = 0.0
    M["form_distinct_bar_frac"] = len({frozenset(sets[b]) for b in sbars}) / n
    # verbatim 4-bar reprise coverage
    wins = {}
    dup = 0; total = 0
    for i in range(n - 3):
        if sbars[i + 3] - sbars[i] == 3 and all(sets[sbars[i + k]] for k in range(4)):
            key = tuple(frozenset(sets[sbars[i + k]]) for k in range(4))
            total += 1
            if key in wins:
                dup += 1
            wins[key] = wins.get(key, 0) + 1
    M["form_reprise_frac"] = dup / total if total else 0.0
    # section count per 100 bars (checkerboard novelty peaks)
    L = min(4, max(1, n // 4))
    nov = np.zeros(n)
    for c in range(n):
        acc = cnt = 0.0
        for a in range(-L, L):
            ii = c + a
            if not (0 <= ii < n):
                continue
            for bb in range(-L, L):
                jj = c + bb
                if not (0 <= jj < n):
                    continue
                acc += (1 if (a < 0) == (bb < 0) else -1) * S[ii, jj]
                cnt += 1
        nov[c] = acc / cnt if cnt else 0
    thr = nov.mean() + 0.5 * nov.std()
    peaks = sum(1 for i in range(1, n - 1) if nov[i] >= thr and nov[i] >= nov[i - 1] and nov[i] >= nov[i + 1])
    M["form_section_per100bars"] = (peaks + 1) / n * 100
    # 29th axis: within-song variation (windowed local-character drift). base_only skips it to avoid
    # recursion when this function is called per-window inside the WSV computation.
    if not base_only:
        try:
            from .within_song_variation import wsv as _wsv
            _v = _wsv(path)
            M["within_song_variation"] = float(_v) if _v is not None else 0.0
        except Exception:
            M["within_song_variation"] = 0.0
    return M


# --------------------------------------------------------------------------- #
def describe(col):
    a = np.array(col, float)
    n = len(a)
    mean, sd = a.mean(), a.std()
    rng = a.max() - a.min()
    # skew / kurtosis (population)
    if sd > 0:
        z = (a - mean) / sd
        skew = float((z ** 3).mean())
        kurt = float((z ** 4).mean())            # non-excess
    else:
        skew = kurt = 0.0
    bc = (skew ** 2 + 1) / kurt if kurt > 0 else 1.0   # bimodality coefficient
    # modal share via 12-bin histogram
    if rng > 0:
        hist, _ = np.histogram(a, bins=12)
        modal_share = hist.max() / n
    else:
        modal_share = 1.0
    distinct = len(set(np.round(a, 6)))
    is_bool = set(np.round(a, 6)) <= {0.0, 1.0}
    degenerate = (rng == 0 or distinct <= 1 or modal_share > DEGEN_MODAL_SHARE
                  or (is_bool and (mean > 0.95 or mean < 0.05)))
    if degenerate:
        shape = "DEGENERATE (rejected)"
    elif bc > 0.60:
        shape = "bimodal/flat"
    elif abs(skew) < 0.8:
        shape = "near-normal"
    else:
        shape = "skewed"
    return dict(mean=mean, sd=sd, min=a.min(), max=a.max(), skew=skew, kurt=kurt,
                bc=bc, modal_share=modal_share, distinct=distinct, shape=shape,
                degenerate=degenerate)


def prune_correlated(names, X):
    """Greedy: drop the metric in the most |r|>=thresh pairs until none remain."""
    keep = list(names)
    idx = {n: i for i, n in enumerate(names)}
    R = np.corrcoef(X.T)
    dropped = []
    redundant_pairs = []
    while True:
        edges = defaultdict(list)
        for i in range(len(keep)):
            for j in range(i + 1, len(keep)):
                r = R[idx[keep[i]], idx[keep[j]]]
                if abs(r) >= CORR_THRESH:
                    edges[keep[i]].append((keep[j], r))
                    edges[keep[j]].append((keep[i], r))
        if not edges:
            break
        # metric with most edges (tie: highest avg |r|)
        worst = max(edges, key=lambda m: (len(edges[m]), np.mean([abs(r) for _, r in edges[m]])))
        for other, r in edges[worst]:
            redundant_pairs.append((worst, other, r))
        dropped.append(worst)
        keep.remove(worst)
    return keep, dropped, R, idx, redundant_pairs


def main():
    truth = json.loads(ANSWER_KEY.read_text(encoding="utf-8"))
    files = sorted(GRAMMAR_DIR.glob("song_*.txt"))
    data = {}
    for f in files:
        try:
            m = metrics_for(Song(f), f)
            if m:
                data[f.stem] = m
        except Exception as e:  # noqa: BLE001
            print(f"[skip] {f.stem}: {e}")
    real = [s for s in sorted(data) if s != GENERATED]
    names = list(next(iter(data.values())).keys())
    X = np.array([[data[s][m] for m in names] for s in real], float)   # 59 x M

    # describe each
    desc = {m: describe(X[:, k]) for k, m in enumerate(names)}
    passed = [m for m in names if not desc[m]["degenerate"]]
    rejected = [m for m in names if desc[m]["degenerate"]]

    # diversity prune on passing metrics
    Xp = np.array([[data[s][m] for m in passed] for s in real], float)
    kept, dropped, R, idx, redundant = prune_correlated(passed, Xp)

    # percentile helper within the 59 real songs
    def pctl(metric, value):
        col = np.array([data[s][metric] for s in real])
        return round(float((col <= value).mean() * 100))

    # ---------- write report ----------
    L = []
    L.append("# Descriptive metric coordinate system (statistical fingerprint)\n")
    L.append("**Descriptive, not evaluative.** Each metric locates a song in statistical space; a "
             "percentile is *typicality/position* within this 59-song corpus, NOT quality. No 'good "
             "music' target exists anywhere here. Corpus = 59 real songs (generated `song_0014` excluded "
             "and used only for validation).\n")
    L.append(f"- Candidate metrics proposed: **{len(names)}** (token-derived: pitch/onset/duration/voice).")
    L.append(f"- Passed discriminating-power filter: **{len(passed)}**; rejected as degenerate: **{len(rejected)}**.")
    L.append(f"- After diversity pruning (|Pearson r| ≥ {CORR_THRESH}): **{len(kept)}** retained as the coordinate system.\n")

    L.append("## Step 3 — discriminating power (distribution shape per metric)\n")
    L.append("| metric | mean | sd | min | max | skew | modal-share | shape |")
    L.append("|---|---|---|---|---|---|---|---|")
    for m in names:
        d = desc[m]
        L.append(f"| `{m}` | {d['mean']:.3f} | {d['sd']:.3f} | {d['min']:.2f} | {d['max']:.2f} | "
                 f"{d['skew']:+.2f} | {d['modal_share']:.2f} | {d['shape']} |")
    L.append("")
    rej_strs = []
    for m in rejected:
        col = np.round(X[:, names.index(m)], 6)
        if set(col) <= {0.0, 1.0}:
            why = "~always true" if desc[m]["mean"] > 0.5 else "~always false"
        else:
            why = f"modal share {desc[m]['modal_share']:.0%}"
        rej_strs.append(f"`{m}` ({why})")
    L.append("**Rejected (degenerate — no discriminating power):** " + (", ".join(rej_strs) or "none"))
    L.append("")

    L.append("## Step 4 — diversity (correlation pruning)\n")
    L.append(f"Dropped as redundant (|r| ≥ {CORR_THRESH} with a kept metric): "
             + (", ".join(f"`{m}`" for m in dropped) or "none") + ".")
    if redundant:
        L.append("\nFlagged redundant pairs (the dropped one vs its correlate):")
        seen = set()
        for a, b, r in redundant:
            k = tuple(sorted((a, b)))
            if k in seen:
                continue
            seen.add(k)
            L.append(f"- `{a}` ↔ `{b}` : r = {r:+.2f}")
    L.append("")
    L.append(f"### Retained coordinate system ({len(kept)} ~independent axes)")
    for m in kept:
        d = desc[m]
        L.append(f"- `{m}` — {d['shape']} (mean {d['mean']:.3f}, sd {d['sd']:.3f}, range [{d['min']:.2f},{d['max']:.2f}])")
    L.append("")

    # correlation matrix among kept
    L.append("### Inter-metric correlation matrix (retained axes, Pearson)")
    short = [m.split("_", 1)[1][:10] if "_" in m else m[:10] for m in kept]
    Rk = np.corrcoef(np.array([[data[s][m] for m in kept] for s in real], float).T)
    L.append("```")
    L.append("            " + " ".join(f"{s:>10}" for s in short))
    for i, m in enumerate(kept):
        L.append(f"{short[i]:>10}  " + " ".join(f"{Rk[i,j]:>+10.2f}" for j in range(len(kept))))
    L.append("```")
    maxoff = max(abs(Rk[i, j]) for i in range(len(kept)) for j in range(i + 1, len(kept))) if len(kept) > 1 else 0
    L.append(f"Max |off-diagonal r| among retained = {maxoff:.2f} (all below the {CORR_THRESH} prune threshold).\n")

    # ---------- fingerprints ----------
    L.append("## Step 6 — statistical fingerprints (percentile profile within the 59 real songs)\n")
    fp_songs = [s for s in FINGERPRINT_SONGS if s in data]
    L.append("| axis | " + " | ".join(f"{truth[s]['artist'].split()[0]} {truth[s]['title'][:14]}" for s in fp_songs) + " |")
    L.append("|---|" + "|".join("---" for _ in fp_songs) + "|")
    for m in kept:
        row = [f"{pctl(m, data[s][m]):>3}%" for s in fp_songs]
        L.append(f"| `{m}` | " + " | ".join(row) + " |")
    L.append("\n(Each cell = that song's percentile on that axis among the 59. A rich fingerprint sits "
             "at DIFFERENT percentiles across axes — not the same percentile everywhere.)\n")

    # ---------- validation: song_0014 ----------
    L.append("## Validation — generated `song_0014` vs the real-song distributions\n")
    if GENERATED in data:
        L.append("Its percentile on each retained axis (≤5% or ≥95% = sits at the corpus extreme):\n")
        L.append("| axis | value | percentile | extreme? |")
        L.append("|---|---|---|---|")
        extremes = []
        for m in kept:
            v = data[GENERATED][m]
            p = pctl(m, v)
            flag = ""
            if p <= 5:
                flag = "◀ low extreme"; extremes.append((m, p, "low"))
            elif p >= 95:
                flag = "▶ high extreme"; extremes.append((m, p, "high"))
            L.append(f"| `{m}` | {v:.3f} | {p}% | {flag} |")
        L.append("")
        if extremes:
            L.append("**Where the generated piece is atypical (extreme percentiles):** "
                     + "; ".join(f"`{m}` {p}% ({d})" for m, p, d in extremes))
        else:
            L.append("(No axis places it beyond the 5th/95th percentile — it sits inside the corpus cloud on the retained axes.)")
    L.append("")
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")

    # cache the corpus reference distribution for fingerprint.py (so it needn't recompute
    # the whole 59-song SSM on every call — it only computes the one target song).
    cache = {
        "metrics": kept,
        "n_real": len(real),
        "corpus": {m: [float(data[s][m]) for s in real] for m in kept},
        "categories": {m: m.split("_", 1)[0] for m in kept},
    }
    (SCRIPT_DIR / "metric_corpus.json").write_text(json.dumps(cache), encoding="utf-8")

    # console
    print(f"songs: {len(real)} real (+1 generated for validation)")
    print("cache written:", SCRIPT_DIR / "metric_corpus.json")
    print(f"candidates {len(names)} -> passed {len(passed)} -> retained {len(kept)} (pruned {len(dropped)} redundant, rejected {len(rejected)} degenerate)")
    print("rejected:", rejected)
    print("dropped redundant:", dropped)
    print("RETAINED:", kept)
    print("written:", OUT)


if __name__ == "__main__":
    main()
