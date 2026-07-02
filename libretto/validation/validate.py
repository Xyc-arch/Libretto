#!/usr/bin/env python3
"""validate.py — external dose-response validation of structural axes.

For each (seed song, axis, dose) we push the axis toward its extreme (its registered lever), hold
instrumentation fixed, render identically, and score with an independent :class:`~libretto.validation.judge`
(default AudioBox-Aesthetics, CE). If an axis captures real, quality-relevant structure, pushing it to an
extreme should make the song sound *worse* to the judge: a NEGATIVE within-song Spearman(dose, score).

Headline statistic = ``within_rho`` = the within-song Spearman(dose, primary), averaged across songs (each
song is its own control, so between-song baseline differences cannot confound it). We also report:
  • ``delta``  = mean score(strongest push) − score(unchanged), the effect EXTENT in the judge's units;
  • ``sign_p`` = one-sided sign test across songs (did they agree on direction more than chance?);
  • ``entangled`` = mean # of OTHER axes that co-moved (re-fingerprinted) — keeps single-axis attribution honest.
An axis is ``validated`` when within_rho ≤ -0.5, every contributing song is negative, and ≥ ``min_songs`` songs
contribute. Rendering is full-length but only a fixed peak-energy window is scored (cheap + avoids missing
edits that fall outside an intro).
"""
import sys
import tempfile
import wave
from dataclasses import dataclass, field
from math import comb
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

from libretto import data_root
from libretto.core.fingerprint import profile
from libretto.core.grammar_to_midi import decode
from .judge import AudioBoxJudge
from .levers import LEVERS, UNCOVERED, perturb

DEFAULT_SONGS = ["song_0047", "song_0009", "song_0016", "song_0006",
                 "song_0174", "song_0194", "song_0143", "song_0312"]
DEFAULT_DOSES = [0.0, 0.33, 0.66, 1.0]
ENTANGLE_THRESH = 15      # percentile points a non-target axis must move to count as "co-moved"
MIN_SONGS = 3             # don't mark an axis validated below this many contributing songs
CLIP_SECONDS = 40         # length of the scored window (None = score the full render)


# --------------------------------------------------------------------------- #
# results
# --------------------------------------------------------------------------- #
@dataclass
class AxisResult:
    axis: str
    push: str
    within_rho: float
    n: int
    n_neg: int
    delta: float
    sign_p: float
    entangled: float
    validated: bool
    per_song: dict = field(default_factory=dict)


@dataclass
class ValidationResult:
    axes: list           # list[AxisResult], sorted most-negative first
    songs: list
    doses: list
    primary: str
    rows: list           # raw per-(song,axis,dose) dicts incl. score columns
    canonical: list      # the canonical axis set (for coverage)
    uncovered: dict      # axis -> reason, for canonical axes with no lever

    @property
    def n_validated(self):
        return sum(a.validated for a in self.axes)

    def coverage(self):
        levered = {a.axis for a in self.axes}
        canon = set(self.canonical)
        return dict(canonical=len(canon), levered=len(levered & canon),
                    extra=sorted(levered - canon), uncovered=dict(self.uncovered))

    def write_csv(self, path):
        cols = ["song", "axis", "push", "dose", "target_pct", "extremity", "entangled",
                "CE", "CU", "PC", "PQ"]
        cols = [c for c in cols if c in (set().union(*[r.keys() for r in self.rows]) if self.rows else [])]
        lines = [",".join(cols)]
        for r in self.rows:
            lines.append(",".join(str(r.get(c, "")) for c in cols))
        Path(path).write_text("\n".join(lines) + "\n")


# --------------------------------------------------------------------------- #
# pure statistics (no IO — unit-testable)
# --------------------------------------------------------------------------- #
def sign_test_p(k, n):
    """One-sided sign test: P(>= k of n agree) under 50/50. k = the majority-direction count."""
    if n == 0:
        return 1.0
    return sum(comb(n, i) for i in range(k, n + 1)) / 2 ** n


def _within_rho(pairs):
    pairs = sorted(pairs)
    d = [p[0] for p in pairs]
    c = [p[1] for p in pairs]
    if len(set(c)) < 2 or len(set(d)) < 2:
        return None
    return float(spearmanr(d, c).correlation)


def summarize(rows, primary="CE", min_songs=MIN_SONGS):
    """rows: per-(song,axis,dose) dicts with 'push', 'dose', 'entangled', and the primary metric.
    Returns sorted list[AxisResult]. Pure — drives the headline numbers and is unit-testable."""
    from collections import defaultdict
    by_axis = defaultdict(lambda: defaultdict(list))   # axis -> song -> [(dose, score)]
    push = {}
    ent = defaultdict(list)
    for r in rows:
        s = r.get(primary)
        if s in (None, ""):
            continue
        by_axis[r["axis"]][r["song"]].append((float(r["dose"]), float(s)))
        push[r["axis"]] = r.get("push", "")
        if float(r["dose"]) > 0:
            ent[r["axis"]].append(float(r.get("entangled", 0)))
    out = []
    for axis, songs in by_axis.items():
        per, deltas = {}, []
        for song, pairs in songs.items():
            rho = _within_rho(pairs)
            if rho is None:
                continue
            per[song] = rho
            pairs.sort()
            deltas.append(pairs[-1][1] - pairs[0][1])
        if not per:
            continue
        vals = list(per.values())
        n, n_neg = len(vals), sum(1 for v in vals if v < 0)
        mean = float(np.mean(vals))
        k = max(n_neg, n - n_neg)
        out.append(AxisResult(
            axis=axis, push=push.get(axis, ""), within_rho=mean, n=n, n_neg=n_neg,
            delta=float(np.mean(deltas)), sign_p=sign_test_p(k, n),
            entangled=float(np.mean(ent[axis])) if ent[axis] else 0.0,
            validated=(mean <= -0.5 and n_neg == n and n >= min_songs), per_song=per))
    out.sort(key=lambda a: a.within_rho)
    return out


def canonical_axes():
    """The canonical axis set (axes_order from the frozen corpus distribution)."""
    import json
    dist = json.loads((data_root() / "corpus_distribution_314.json").read_text())
    return list(dist["axes_order"])


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #
def _soundfont():
    import os
    cands = [os.environ.get("LIBRETTO_SOUNDFONT"),
             "/Applications/MuseScore 4.app/Contents/Resources/sound/MS Basic.sf3",
             str(Path(sys.prefix) / "lib/python3.11/site-packages/pretty_midi/TimGM6mb.sf2")]
    for c in cands:
        if c and Path(c).exists():
            return c
    raise FileNotFoundError("no soundfont found; set $LIBRETTO_SOUNDFONT to a .sf2/.sf3 file")


def _render(text, mid, wav, sf):
    import subprocess
    txt = mid.with_suffix(".txt")
    txt.write_text(text, encoding="utf-8")
    decode(str(txt), str(mid))
    subprocess.run(["fluidsynth", "-ni", "-g", "0.7", "-r", "22050", "-F", str(wav), sf, str(mid)],
                   check=True, capture_output=True)
    return txt


def _read_mono(path):
    with wave.open(str(path), "rb") as w:
        fr, nch, n = w.getframerate(), w.getnchannels(), w.getnframes()
        raw = np.frombuffer(w.readframes(n), dtype=np.int16)
    return (raw.reshape(-1, nch).mean(axis=1) if nch > 1 else raw), fr


def _peak_window_start(path, seconds):
    if seconds is None:
        return 0.0
    mono, fr = _read_mono(path)
    total = len(mono) / fr
    if total <= seconds:
        return 0.0
    nb = len(mono) // fr
    if nb <= seconds:
        return 0.0
    energy = (mono[: nb * fr].astype(np.float64) ** 2).reshape(nb, fr).mean(axis=1)
    win = int(round(seconds))
    csum = np.concatenate([[0.0], np.cumsum(energy)])
    sums = csum[win:] - csum[:-win]
    return float(min(int(np.argmax(sums)), max(0, total - seconds)))


def _trim(path, seconds, start):
    with wave.open(str(path), "rb") as w:
        params = w.getparams()
        fr, total = w.getframerate(), w.getnframes()
        s = min(total, int(start * fr))
        w.setpos(s)
        frames = w.readframes(min(total - s, int(fr * seconds)))
    with wave.open(str(path), "wb") as w:
        w.setparams(params)
        w.writeframes(frames)


def _extremity(pct, push):
    return pct if push == "high" else 100 - pct


# --------------------------------------------------------------------------- #
# the validation run
# --------------------------------------------------------------------------- #
def validate(songs=None, axes=None, judge=None, doses=None, grammar_dir=None,
             clip_seconds=CLIP_SECONDS, entangle_thresh=ENTANGLE_THRESH, min_songs=MIN_SONGS,
             progress=print):
    """Run the dose-response validation. Returns a :class:`ValidationResult`.

    songs: seed song ids (default 8 genre-spread). axes: iterable of axis names to test (default = all
    registered levers). judge: a Judge (default AudioBoxJudge). doses: list incl. 0.0 (default 4 points).
    """
    songs = list(songs or DEFAULT_SONGS)
    doses = list(doses or DEFAULT_DOSES)
    judge = judge or AudioBoxJudge()
    levers = {a: LEVERS[a] for a in (axes or LEVERS)} if axes else dict(LEVERS)
    gdir = Path(grammar_dir or (data_root() / "grammar"))
    sf = _soundfont()

    rows = []
    with tempfile.TemporaryDirectory(prefix="axisval_") as td:
        tmp = Path(td)
        for song in songs:
            base_text = (gdir / f"{song}.txt").read_text(encoding="utf-8")
            base_prof = {k: v["percentile"] for k, v in profile(gdir / f"{song}.txt")[0].items()}
            base_wav = tmp / f"{song}__base.wav"
            _render(base_text, tmp / f"{song}__base.mid", base_wav, sf)
            win = _peak_window_start(base_wav, clip_seconds) if clip_seconds is not None else 0.0
            if clip_seconds is not None:
                _trim(base_wav, clip_seconds, win)
            for axis, lev in levers.items():
                rows.append(dict(song=song, axis=axis, push=lev.push, dose=0.0,
                                 target_pct=base_prof.get(axis), extremity=_extremity(base_prof.get(axis, 0), lev.push),
                                 entangled=0, wav=str(base_wav)))
                for dose in doses:
                    if dose <= 0:
                        continue
                    text = perturb(base_text, axis, dose)
                    wav = tmp / f"{song}__{axis}__{dose}.wav"
                    txt = _render(text, tmp / f"{song}__{axis}__{dose}.mid", wav, sf)
                    if clip_seconds is not None:
                        _trim(wav, clip_seconds, win)
                    prof = {k: v["percentile"] for k, v in profile(txt)[0].items()}
                    ent = sum(1 for k in prof if k != axis and abs(prof[k] - base_prof.get(k, prof[k])) > entangle_thresh)
                    rows.append(dict(song=song, axis=axis, push=lev.push, dose=dose,
                                     target_pct=prof.get(axis), extremity=_extremity(prof.get(axis, 0), lev.push),
                                     entangled=ent, wav=str(wav)))
            progress(f"  rendered {song}")

        uniq = sorted({r["wav"] for r in rows})
        progress(f"scoring {len(uniq)} unique clips with {type(judge).__name__} (primary={judge.primary})...")
        scores = {d["path"]: d for d in judge.score(uniq)}
        metrics = getattr(judge, "METRICS", (judge.primary,))
        for r in rows:
            s = scores.get(r["wav"], {})
            for m in metrics:
                r[m] = s.get(m)
            r.pop("wav", None)

    axesres = summarize(rows, primary=judge.primary, min_songs=min_songs)
    canon = canonical_axes()
    uncov = {a: r for a, r in UNCOVERED.items() if a in canon}
    return ValidationResult(axes=axesres, songs=songs, doses=doses, primary=judge.primary,
                            rows=rows, canonical=canon, uncovered=uncov)
