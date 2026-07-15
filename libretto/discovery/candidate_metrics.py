#!/usr/bin/env python3
"""candidate_metrics.py — CANDIDATE axis library for autonomous axis discovery.

The 28 frozen base metrics (via metric_discovery.metrics_for) PLUS new candidate families that the
enriched grammar (GM programs, drum voices, per-note velocity) finally makes computable:
  * DYNAMICS  — from note velocities
  * PERCUSSION — from drum voices
  * INSTRUMENTATION — from voice programs

These are CANDIDATES only: the discovery loop decides which survive the spread / decorrelation / genre-
discrimination gates. This module NEVER edits the frozen metric_discovery.py — it composes on top of it.
"""
import math
from collections import Counter

from libretto.core import metric_discovery as md


def _entropy(counts):
    tot = sum(counts)
    if tot <= 0:
        return 0.0
    ps = [c / tot for c in counts if c > 0]
    h = -sum(p * math.log2(p) for p in ps)
    n = len([c for c in counts if c > 0])
    return h / math.log2(n) if n > 1 else 0.0        # normalized 0..1


def _cv(xs):
    if not xs:
        return 0.0
    m = sum(xs) / len(xs)
    if m == 0:
        return 0.0
    var = sum((x - m) ** 2 for x in xs) / len(xs)
    return math.sqrt(var) / abs(m)


# ---------------------------------------------------------------------------- DYNAMICS
def dynamics_metrics(song):
    vels = [e["vel"] for e in song.events if e.get("vel") is not None]
    if not vels:
        return {"dyn_vel_mean": 0.0, "dyn_vel_cv": 0.0, "dyn_vel_range": 0.0, "dyn_accent_rate": 0.0}
    m = sum(vels) / len(vels)
    sd = (sum((v - m) ** 2 for v in vels) / len(vels)) ** 0.5
    return {
        "dyn_vel_mean": m / 127.0,                                   # overall loudness 0..1
        "dyn_vel_cv": (sd / m) if m else 0.0,                        # dynamic contrast
        "dyn_vel_range": (max(vels) - min(vels)) / 127.0,            # loudest-softest span
        "dyn_accent_rate": sum(1 for v in vels if v > m + sd) / len(vels),  # accented notes
    }


# ---------------------------------------------------------------------------- PERCUSSION
def percussion_metrics(song):
    dv = getattr(song, "drum_voices", set()) or set()
    dev = [e for e in song.events if e["voice"] in dv]
    nb = max(1, getattr(song, "n_bars", 1))
    if not dev:
        return {"perc_present": 0.0, "perc_density": 0.0, "perc_pos_entropy": 0.0, "perc_backbeat": 0.0}
    bars_with = len({e["bar"] for e in dev})
    # onset position within bar (in beats) -> regularity via entropy; backbeat = beats 2 & 4
    beats = getattr(song, "bar_ql", 4.0) or 4.0
    pos = Counter(round(e.get("onb", 0.0)) for e in dev)
    backbeat = sum(c for p, c in pos.items() if p in (1, 3)) / len(dev)   # 0-indexed beats 2,4
    return {
        "perc_present": bars_with / nb,                              # how much of the song has drums
        "perc_density": len(dev) / nb,                               # hits per bar
        "perc_pos_entropy": _entropy(list(pos.values())),            # groove regularity (low=locked)
        "perc_backbeat": backbeat,                                   # backbeat emphasis
    }


# ---------------------------------------------------------------------------- INSTRUMENTATION
def instrumentation_metrics(song):
    vp = getattr(song, "voice_programs", {}) or {}
    if not vp:
        return {"inst_n_programs": 0.0, "inst_program_entropy": 0.0,
                "inst_family_spread": 0.0, "inst_pitched_voices": 0.0}
    # weight programs by that voice's note count
    note_by_voice = Counter(e["voice"] for e in song.events if e["voice"] not in getattr(song, "drum_voices", set()))
    prog_weight = Counter()
    for v, p in vp.items():
        prog_weight[p] += note_by_voice.get(v, 0) or 1
    families = {p // 8 for p in vp.values()}                          # 16 GM families
    return {
        "inst_n_programs": len(set(vp.values())) / 16.0,             # distinct instruments (scaled)
        "inst_program_entropy": _entropy(list(prog_weight.values())), # even vs dominant instrument
        "inst_family_spread": len(families) / 16.0,                  # timbral breadth
        "inst_pitched_voices": min(len(vp), 16) / 16.0,              # ensemble size (scaled)
    }


NEW_CANDIDATES = ["dyn_vel_mean", "dyn_vel_cv", "dyn_vel_range", "dyn_accent_rate",
                  "perc_present", "perc_density", "perc_pos_entropy", "perc_backbeat",
                  "inst_n_programs", "inst_program_entropy", "inst_family_spread", "inst_pitched_voices"]


def candidate_vector(song, path):
    """Full candidate metric dict: the 28 frozen base metrics + the new enriched-data candidates."""
    out = dict(md.metrics_for(song, path))              # 28 frozen base axes (unchanged)
    out.update(dynamics_metrics(song))
    out.update(percussion_metrics(song))
    out.update(instrumentation_metrics(song))
    return out
