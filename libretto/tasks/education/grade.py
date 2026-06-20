#!/usr/bin/env python3
"""grade.py — comprehensive difficulty grader + training-content detector for a practice piece.

`difficulty_grade(path)` rates a single-voice piano piece across weighted factors (tempo, note density, note
values, syncopation, rhythmic variety, melodic range/leaps, chromaticism, hand-span/polyphony, meter, key
signature) -> a continuous 0-100 score + a 1-10 grade, with the per-factor breakdown and top drivers. There
is NO hard beginner/intermediate/advanced cutoff — difficulty is the score itself.

`detect_training(path)` scans the piece and outputs the TRAINING KEYWORDS it actually exercises (meter, tempo,
scale/key, syncopation amount, note values present, melodic/textural devices, chord qualities) — an automatic
"what does this drill train" label, independent of any requested spec.
"""
import math
import statistics
from collections import Counter
from pathlib import Path

from libretto.core import Song
from . import measure as M
from . import curriculum as C


def _clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def _key_accidentals(key):
    """# of sharps/flats in the declared key signature (minor -> relative major). Reading-load proxy."""
    tonic_pc, _, mode = M.scale_pcs(key)
    if "minor" in mode or mode in ("aeolian", "dorian", "phrygian", "locrian"):
        tonic_pc = (tonic_pc + 3) % 12
    acc = {0: 0, 7: 1, 2: 2, 9: 3, 4: 4, 11: 5, 6: 6, 5: 1, 10: 2, 3: 3, 8: 4, 1: 5}
    return acc.get(tonic_pc, 3)


_METER_DIFF = {"4/4": 0.10, "3/4": 0.20, "2/4": 0.20, "6/8": 0.50, "9/8": 0.80, "12/8": 0.70}


def _features(path):
    s = Song(path); ev = s.events; text = Path(path).read_text()
    meter, tempo = M._header(text); bu = M._beat_unit(meter)
    nbars = max(1, len({e["bar"] for e in ev}))
    durs = [e["dur"] for e in ev]
    med = statistics.median(durs) if durs else 1.0
    opb = len(ev) / nbars
    iv = M._melodic_intervals(ev)
    mids = [e["midi"] for e in ev]
    rng = (max(mids) - min(mids)) if mids else 0
    leap_frac = (sum(1 for i in iv if i >= 3) / len(iv)) if iv else 0.0
    return dict(meter=meter, tempo=tempo or 90, bu=bu, nbars=nbars, durs=durs, med=med, opb=opb,
                iv=iv, rng=rng, leap_frac=leap_frac, sim=M._max_simultaneity(ev), ev=ev, text=text)


def difficulty_grade(path, key=None):
    f = _features(path); text = f["text"]
    key = key or _guess_key(f["ev"], text)
    _, pcs, _ = M.scale_pcs(key)
    out_frac = (sum(1 for e in f["ev"] if e["midi"] % 12 not in pcs) / len(f["ev"])) if f["ev"] else 0.0
    triplet = "grid:12t" in text
    n_distinct_dur = len(set(round(d, 2) for d in f["durs"]))
    # widest simultaneous interval (hand span)
    span = 0
    by = {}
    for e in f["ev"]:
        by.setdefault((e["bar"], round(e["onb"], 3)), []).append(e["midi"])
    for ms in by.values():
        if len(ms) > 1:
            span = max(span, max(ms) - min(ms))

    factors = {
        "tempo":            (_clamp((f["tempo"] - 60) / 120), 0.12),
        "note_density":     (_clamp((f["opb"] - 2) / 10), 0.14),
        "note_values":      (_clamp((1.25 - f["med"]) / 1.0) + (0.15 if triplet else 0), 0.14),
        "syncopation":      (_clamp(M._offbeat_ratio(f["ev"], f["bu"])), 0.14),
        "rhythmic_variety": (_clamp(n_distinct_dur / 6) + (0.1 if triplet else 0), 0.10),
        "melodic_range_leaps": (_clamp(f["rng"] / 24) * 0.5 + f["leap_frac"] * 0.5, 0.12),
        "chromaticism":     (_clamp(out_frac * 4), 0.08),
        "hand_span_polyphony": (_clamp(span / 24) * 0.6 + _clamp((f["sim"] - 1) / 3) * 0.4, 0.08),
        "meter":            (_METER_DIFF.get(f["meter"], 0.6), 0.04),
        "key_signature":    (_clamp(_key_accidentals(key) / 6), 0.04),
    }
    score = sum(_clamp(v) * w for v, w in factors.values())
    score100 = round(score * 100, 1)
    grade10 = max(1, min(10, round(score * 9 + 1)))
    # No hard beginner/intermediate/advanced cutoff — difficulty is a continuous score; the per-factor
    # breakdown + top drivers say WHY. (Callers can bucket the score themselves if they need labels.)
    return {
        "path": Path(path).name, "key_assumed": key, "score_0_100": score100, "grade_1_10": grade10,
        "factors": {k: {"value": round(_clamp(v), 3), "weight": w, "contribution": round(_clamp(v) * w * 100, 1)}
                    for k, (v, w) in factors.items()},
        "top_drivers": [k for k, _ in sorted(factors.items(), key=lambda kv: -_clamp(kv[1][0]) * kv[1][1])[:3]],
    }


def _guess_key(events, text):
    """Best-fit major/minor key from the note pitch-class histogram (fallback when none is given)."""
    if not events:
        return "C major"
    hist = Counter(e["midi"] % 12 for e in events)
    best = ("C major", -1)
    for tonic in range(12):
        for mode in ("major", "natural minor"):
            pcs = set((tonic + i) % 12 for i in M.SCALES[mode])
            score = sum(c for pc, c in hist.items() if pc in pcs)
            name = f"{_PC_NAME[tonic]} {'major' if mode == 'major' else 'minor'}"
            if score > best[1]:
                best = (name, score)
    return best[0]


_PC_NAME = {0: "C", 1: "C#", 2: "D", 3: "Eb", 4: "E", 5: "F", 6: "F#", 7: "G", 8: "Ab", 9: "A", 10: "Bb", 11: "B"}


def detect_training(path, key=None):
    """Auto-label what the piece TRAINS: a list of training keyword tags (+ evidence)."""
    s = Song(path); ev = s.events; text = Path(path).read_text()
    meter, tempo = M._header(text); bu = M._beat_unit(meter)
    key = key or _guess_key(ev, text)
    tags = []

    tags.append({"tag": f"meter:{meter}", "detail": meter})
    # tempo word (nearest)
    tw = min(C.TEMPO_WORDS.items(), key=lambda kv: abs(kv[1] - (tempo or 90)))
    tags.append({"tag": f"tempo:{tw[0]}({tempo}bpm)", "detail": tempo})
    tags.append({"tag": f"key:{key}", "detail": key})

    # syncopation amount band
    r = round(M._offbeat_ratio(ev, bu), 2)
    band = next((name for name, (lo, hi) in [("straight", (0, 0.08)), ("light", (0.08, 0.32)),
                 ("moderate", (0.32, 0.55)), ("heavy", (0.55, 1.01))] if lo <= r < hi), "moderate")
    tags.append({"tag": f"syncopation:{band}({r})", "detail": r})

    # note values present
    durs = [round(e["dur"], 3) for e in ev]
    vmap = [(0.25, "sixteenths"), (0.5, "eighths"), (1.0, "quarters"), (1.5, "dotted"),
            (2.0, "halves"), (4.0, "wholes")]
    present = sorted({name for d in durs for val, name in vmap if abs(d - val) < 0.05})
    if "grid:12t" in text:
        present.append("triplets")
    if present:
        tags.append({"tag": "note-values:" + "+".join(present), "detail": present})

    # melodic / textural devices
    iv = M._melodic_intervals(ev)
    if iv:
        step = sum(1 for i in iv if i <= 2) / len(iv)
        if step >= 0.6:
            tags.append({"tag": "melody:stepwise", "detail": round(step, 2)})
        if any(i >= 5 for i in iv) or (sum(1 for i in iv if i >= 3) / len(iv)) >= 0.3:
            tags.append({"tag": "melody:leaps", "detail": max(iv)})
    # sixteenth runs (>=4 consecutive sixteenths)
    run = mx = 0
    for e in sorted(ev, key=lambda e: (e["bar"], e["onb"])):
        if abs(e["dur"] - 0.25) < 0.05:
            run += 1; mx = max(mx, run)
        else:
            run = 0
    if mx >= 4:
        tags.append({"tag": "device:sixteenth-runs", "detail": mx})
    # ties (sustained across a beat)
    for e in ev:
        nb = (math.floor(round(e["onb"] / bu, 6)) + 1) * bu
        if e["onb"] < nb < e["onb"] + e["dur"] - 1e-6:
            tags.append({"tag": "device:ties", "detail": "note held across a beat"}); break
    # texture
    sim = M._max_simultaneity(ev)
    barpcs = {}
    for e in ev:
        barpcs.setdefault(e["bar"], set()).add(e["midi"] % 12)
    maxpcs = max((len(v) for v in barpcs.values()), default=0)
    if sim >= 3:
        tags.append({"tag": "texture:block-chords", "detail": f"max {sim} notes together"})
    elif maxpcs >= 3:
        tags.append({"tag": "texture:broken-chords/arpeggio", "detail": f"{maxpcs} chord pcs/bar, {sim} together"})
    else:
        tags.append({"tag": "texture:single-line", "detail": f"max simultaneity {sim}"})

    # chord qualities from the labels
    labels = M._chord_labels(text)
    quals = Counter()
    for c in labels:
        if "maj7" in c.lower(): quals["maj7"] += 1
        elif c.endswith("7"): quals["dom7"] += 1
        elif "dim" in c.lower(): quals["diminished"] += 1
        elif "aug" in c.lower(): quals["augmented"] += 1
        elif c[-1:] == "m" or c[-2:] in ("m7",) or (len(c) > 1 and c[1:2] == "m"): quals["minor"] += 1
        else: quals["major"] += 1
    if quals:
        tags.append({"tag": "chords:" + ",".join(f"{k}" for k, _ in quals.most_common()), "detail": dict(quals)})

    return {"path": Path(path).name, "key_assumed": key, "training_tags": [t["tag"] for t in tags],
            "evidence": tags}


def analyze(path, key=None):
    g = difficulty_grade(path, key=key); t = detect_training(path, key=key)
    return {"difficulty": g, "training": t}
