#!/usr/bin/env python3
"""
understanding_probe.py — does an LLM actually UNDERSTAND music, or pattern-match names?

The model reads a blind (anonymized) text score and makes FALSIFIABLE factual claims.
Each claim is graded against HARD GROUND TRUTH computed directly from the note data
(pitch / onset / duration / voice) parsed from the same grammar the model saw.

CORE PRINCIPLE (never violated): a claim is gradeable only if it can be checked exactly
from note-level data. We NEVER grade against this project's chord labeler, section
detector, or key analyzer — that would measure agreement-with-our-heuristic, not
understanding. (music21's independent chord guess is reported separately, labeled
"reference, not truth".)

Run order:
  1. Grader self-test (pure Python, no API) — grades known-true and known-false claims on
     one song and asserts the verdicts are right. ALWAYS runs first.
  2. If an API credential is present: elicit claims for every song, grade, and report
     per-category accuracy vs naive baselines + a fame/memorization correlation.
     No credential -> stop after the self-test.
"""
import json
import math
import re
import sys
from collections import Counter, defaultdict
import os
from pathlib import Path

# ============================ TUNABLE CONSTANTS ============================= #
NEURAL_MODEL = "claude-opus-4-8"
CHORD_BARS = 3                 # how many bars the model must analyze for chord-by-constituents
NEURAL_MAX_TOKENS = 3000

# grading tolerances (all explicit)
SPAN_TOL = 1                   # semitones, melodic-span match
DUR_TOL = 0.25                 # beats, longest-note match
NEAR_IDENTICAL_JACCARD = 0.90  # two bars "near-identical" if note-event Jaccard >= this
SCALE_MASS_THRESH = 0.90       # >= this fraction of pitch-mass in-scale => scale claim fits
SYNCOPATION_FRAC = 0.15        # >= this fraction of onsets off-beat => syncopation present
ONSET_EPS = 0.03               # beats, tolerance when matching simultaneous onsets/grids
# =========================================================================== #

SCRIPT_DIR = Path(os.environ.get("LIBRETTO_DATA") or (Path(__file__).resolve().parent.parent / "data"))
GRAMMAR_DIR = SCRIPT_DIR / "grammar"
ANSWER_KEY = SCRIPT_DIR / "answer_key" / "grammar_truth.json"

_PITCH_BASE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_PITCH_RE = re.compile(r"^([A-Ga-g])([#b]*)(-?\d+)$")
_BAR_RE = re.compile(r"^@(\d+)\s+\[(.*?)\](?:\s+\(grid:(\w+)\))?\s*$")
# token: pitches @onset >dur  (optional ^velocity suffix, optional). velocity is coarse 1..127.
_TOKEN_RE = re.compile(r"^(.+?)@(\d+)>(\d+)(?:\^(\d+))?$")
_GRID_RE = re.compile(r"(\d+)")
# a voice label in the VOICES header may carry an annotation: "Name[prog=33]" or "Name[drums]".
_VOICE_ANNOT_RE = re.compile(r"^(.*?)\s*\[(.*?)\]\s*$")
PC_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

SCALE_INTERVALS = {
    "major": (0, 2, 4, 5, 7, 9, 11), "ionian": (0, 2, 4, 5, 7, 9, 11),
    "minor": (0, 2, 3, 5, 7, 8, 10), "natural minor": (0, 2, 3, 5, 7, 8, 10),
    "aeolian": (0, 2, 3, 5, 7, 8, 10),
    "dorian": (0, 2, 3, 5, 7, 9, 10), "phrygian": (0, 1, 3, 5, 7, 8, 10),
    "lydian": (0, 2, 4, 6, 7, 9, 11), "mixolydian": (0, 2, 4, 5, 7, 9, 10),
    "locrian": (0, 1, 3, 5, 6, 8, 10),
    "harmonic minor": (0, 2, 3, 5, 7, 8, 11), "melodic minor": (0, 2, 3, 5, 7, 9, 11),
}


def parse_pc(name):
    name = name.strip()
    m = re.match(r"^([A-Ga-g])([#b]*)$", name) or _PITCH_RE.match(name)
    if not m:
        return None
    pc = _PITCH_BASE[m.group(1).upper()]
    for a in m.group(2):
        pc += 1 if a == "#" else -1
    return pc % 12


def parse_pitch_midi(name):
    m = _PITCH_RE.match(name.strip())
    if not m:
        return None
    pc = _PITCH_BASE[m.group(1).upper()]
    for a in m.group(2):
        pc += 1 if a == "#" else -1
    octave = int(m.group(3))
    return (octave + 1) * 12 + pc


def grid_int(label):
    m = _GRID_RE.search(label or "")
    return int(m.group(1)) if m else 16


# --------------------------------------------------------------------------- #
# Note-level parse of a grammar file  ->  the ground-truth substrate.
# --------------------------------------------------------------------------- #
class Song:
    def __init__(self, path):
        lines = Path(path).read_text(encoding="utf-8").splitlines()
        head = dict(re.findall(r"(\w+):\s*([^|]+?)\s*(?:\||$)", lines[0]))
        mm = re.match(r"(\d+)\s*/\s*(\d+)", head.get("METER", "4/4"))
        num, den = (int(mm.group(1)), int(mm.group(2))) if mm else (4, 4)
        self.bar_ql = num * 4.0 / den           # beats (quarter-notes) per bar
        self.default_grid = grid_int(head.get("GRID", "16th"))
        self.n_bars = int(_GRID_RE.search(head.get("BARS", "0")).group(1)) if head.get("BARS") else 0
        raw_voices = ([v.strip() for v in lines[1].split(":", 1)[1].split(",")]
                      if len(lines) > 1 and lines[1].startswith("VOICES") else [])
        # A voice label may carry a "[prog=N]" GM-program or "[drums]" annotation. Strip it to
        # get the bare voice name (what note lines key off), and record it for the decoder.
        self.voices = []                       # bare names (backward-compatible)
        self.voice_programs = {}               # bare name -> GM program (0..127), if declared
        self.drum_voices = set()               # bare names flagged [drums]
        for rv in raw_voices:
            am = _VOICE_ANNOT_RE.match(rv)
            if am:
                bare, annot = am.group(1).strip(), am.group(2).strip().lower()
                if annot == "drums" or annot == "drum":
                    self.drum_voices.add(bare)
                else:
                    pm2 = re.match(r"prog\s*=\s*(\d+)", annot)
                    if pm2:
                        self.voice_programs[bare] = int(pm2.group(1)) & 127
                self.voices.append(bare)
            else:
                self.voices.append(rv)
        # events: one per sounding pitch
        self.events = []        # dict(voice, bar, onb (beats in bar), abs (beats), dur (beats), midi, pc, vel)
        cur_bar, cur_grid = None, self.default_grid
        for ln in lines[2:]:
            bm = _BAR_RE.match(ln)
            if bm:
                cur_bar = int(bm.group(1))
                cur_grid = grid_int(bm.group(3)) if bm.group(3) else self.default_grid
                continue
            if cur_bar is None or not ln.startswith(" "):
                continue
            name, _, rest = ln.strip().partition(":")
            name = name.strip()
            slot_ql = 4.0 / cur_grid
            for tok in rest.split():
                tm = _TOKEN_RE.match(tok)
                if not tm:
                    continue
                onb = (int(tm.group(2)) - 1) * slot_ql
                dur = int(tm.group(3)) * slot_ql
                vel = int(tm.group(4)) if tm.group(4) else None    # coarse velocity, if declared
                ab = (cur_bar - 1) * self.bar_ql + onb
                for p in tm.group(1).split("+"):
                    midi = parse_pitch_midi(p)
                    if midi is None:
                        continue
                    self.events.append(dict(voice=name, bar=cur_bar, onb=round(onb, 4),
                                            abs=round(ab, 4), dur=round(dur, 4),
                                            midi=midi, pc=midi % 12, vel=vel))

    # --- helpers used by both ground-truth and grading ---
    def midis(self):
        return [e["midi"] for e in self.events]

    def voice_events(self, voice):
        return [e for e in self.events if e["voice"] == voice]

    def onset_count(self, voice=None):
        """distinct onset events (chord = one onset)"""
        s = {(e["voice"], e["abs"]) for e in self.events if voice is None or e["voice"] == voice}
        return len(s)

    def most_active_voice(self):
        c = Counter()
        for v in self.voices:
            c[v] = len({e["abs"] for e in self.voice_events(v)})
        return c.most_common(1)[0][0] if c else None

    def voice_span(self, voice):
        ms = [e["midi"] for e in self.voice_events(voice)]
        return (max(ms) - min(ms)) if ms else 0

    def bar_onsets(self, bar):
        return {(e["voice"], e["abs"]) for e in self.events if e["bar"] == bar}

    def bar_pcs(self, bar):
        return {e["pc"] for e in self.events if e["bar"] == bar}

    def bar_event_set(self, bar):
        """note events of a bar as (voice, onset-in-bar, midi) — for repetition similarity."""
        return {(e["voice"], e["onb"], e["midi"]) for e in self.events if e["bar"] == bar}

    def distinct_pcs(self):
        return {e["pc"] for e in self.events}

    def pc_weight(self):
        w = defaultdict(float)
        for e in self.events:
            w[e["pc"]] += e["dur"]
        return w

    def line(self, voice):
        """melodic line: (abs_onset -> top midi) at each onset of the voice."""
        by = defaultdict(list)
        for e in self.voice_events(voice):
            by[e["abs"]].append(e["midi"])
        return {t: max(ms) for t, ms in by.items()}

    def sounding_midis(self, voice, t):
        return [e["midi"] for e in self.voice_events(voice)
                if e["abs"] - ONSET_EPS <= t < e["abs"] + e["dur"] - 1e-9]


def bar_similarity(song, b1, b2):
    a, b = song.bar_event_set(b1), song.bar_event_set(b2)
    if not a and not b:
        return 1.0
    u = a | b
    return len(a & b) / len(u) if u else 0.0


# --------------------------------------------------------------------------- #
# GROUND TRUTH per song (no model involved) + best-constant baselines.
# --------------------------------------------------------------------------- #
_GT_CACHE = {}


def ground_truth(song):
    if id(song) in _GT_CACHE:
        return _GT_CACHE[id(song)]
    ms = song.midis()
    durs = [e["dur"] for e in song.events]
    bars = sorted({e["bar"] for e in song.events})
    dens = Counter(e["bar"] for e in song.events)  # density by note count
    mav = song.most_active_voice()
    # max bar-pair similarity (for the repetition baseline / "none" grading).
    # Precompute each bar's event set once, then pairwise; early-exit once we cross the
    # near-identical threshold (only the >=threshold boolean matters downstream).
    sets = {b: song.bar_event_set(b) for b in bars}
    max_sim = 0.0
    done = False
    for i in range(len(bars)):
        if done:
            break
        ai = sets[bars[i]]
        for j in range(i + 1, len(bars)):
            bj = sets[bars[j]]
            u = ai | bj
            s = (len(ai & bj) / len(u)) if u else 1.0
            if s > max_sim:
                max_sim = s
            if max_sim >= NEAR_IDENTICAL_JACCARD:
                done = True
                break
    gt = {
        "highest_midi": max(ms) if ms else None,
        "lowest_midi": min(ms) if ms else None,
        "most_active_voice": mav,
        "active_span": song.voice_span(mav) if mav else 0,
        "longest_beats": max(durs) if durs else 0,
        "any_longer_than_bar": any(d > song.bar_ql + 1e-6 for d in durs),
        "densest_bar": dens.most_common(1)[0][0] if dens else None,
        "max_bar_sim": max_sim,
        "distinct_pc_count": len(song.distinct_pcs()),
        "present_pcs": song.distinct_pcs(),
        "subdivision": _subdivision(song),
        "syncopation": _syncopation(song),
        "note_value": _predominant_value(durs),
    }
    _GT_CACHE[id(song)] = gt
    return gt


def _subdivision(song):
    bin_hits = trip_hits = 0
    for e in song.events:
        frac = e["onb"] % 1.0
        b = min(abs(frac - x) for x in (0.0, 0.25, 0.5, 0.75, 1.0))
        t = min(abs(frac - x) for x in (0.0, 1 / 3, 2 / 3, 1.0))
        if t + 1e-9 < b:
            trip_hits += 1
        else:
            bin_hits += 1
    return "triplet" if trip_hits > bin_hits else "straight"


def _syncopation(song):
    on = [e for e in song.events]
    if not on:
        return False
    off = sum(1 for e in on if (e["onb"] % 1.0) > 1e-6)
    return (off / len(on)) >= SYNCOPATION_FRAC


_VALUE_TABLE = [(4.0, "whole"), (3.0, "dotted half"), (2.0, "half"), (1.5, "dotted quarter"),
                (1.0, "quarter"), (0.75, "dotted eighth"), (2 / 3, "eighth triplet"),
                (0.5, "eighth"), (1 / 3, "eighth triplet"), (0.25, "sixteenth")]


def _value_name(d):
    return min(_VALUE_TABLE, key=lambda kv: abs(kv[0] - d))[1]


def _predominant_value(durs):
    if not durs:
        return None
    names = Counter(_value_name(d) for d in durs)
    return names.most_common(1)[0][0]


def baselines(truths):
    """Best single-constant-guess accuracy per metric (so 'above chance' is meaningful)."""
    def const_acc(values, tol=None):
        vals = [v for v in values if v is not None]
        if not vals:
            return 0.0
        if tol is None:
            c = Counter(vals)
            return c.most_common(1)[0][1] / len(vals)
        # numeric tolerance: best constant = value covering most within tol
        best = 0
        for guess in set(vals):
            best = max(best, sum(1 for v in vals if abs(v - guess) <= tol))
        return best / len(vals)

    b = {}
    b["range:highest"] = const_acc([t["highest_midi"] for t in truths])
    b["range:lowest"] = const_acc([t["lowest_midi"] for t in truths])
    b["range:active_voice"] = const_acc([t["most_active_voice"] for t in truths])
    b["range:span"] = const_acc([t["active_span"] for t in truths], SPAN_TOL)
    b["rhythm_basic:longest"] = const_acc([t["longest_beats"] for t in truths], DUR_TOL)
    p = sum(t["any_longer_than_bar"] for t in truths) / len(truths)
    b["rhythm_basic:over_bar"] = max(p, 1 - p)
    b["rhythm_basic:densest"] = const_acc([t["densest_bar"] for t in truths])
    # repetition: naive "always say there IS a near-identical pair" (almost always true)
    p = sum(t["max_bar_sim"] >= NEAR_IDENTICAL_JACCARD for t in truths) / len(truths)
    b["repetition"] = max(p, 1 - p)
    b["pitch_content:count"] = const_acc([t["distinct_pc_count"] for t in truths])
    # pc present: guessing "present" for a random pc => mean fraction of pcs present
    b["pitch_content:present"] = sum(len(t["present_pcs"]) / 12 for t in truths) / len(truths)
    # voice relations: probability a random pair / interval ever occurs (computed per song below)
    b["voice_rel:parallel"] = 0.5
    b["voice_rel:interval"] = 0.5
    p = sum(t["subdivision"] == "straight" for t in truths) / len(truths)
    b["rhythm_type:subdivision"] = max(p, 1 - p)
    p = sum(t["syncopation"] for t in truths) / len(truths)
    b["rhythm_type:syncopation"] = max(p, 1 - p)
    b["rhythm_type:note_value"] = const_acc([t["note_value"] for t in truths])
    b["scale_mode"] = const_acc(["C major fit" for _ in truths])  # placeholder; set in report
    b["chord_constituents"] = 0.5
    return b


# --------------------------------------------------------------------------- #
# GRADERS — each returns a list of (category, score 0..1, detail string).
# --------------------------------------------------------------------------- #
def grade(song, claim):
    gt = ground_truth(song)
    out = []

    # ---- range ----
    r = claim.get("range", {})
    hi = parse_pitch_midi(str(r.get("highest_pitch", "")))
    lo = parse_pitch_midi(str(r.get("lowest_pitch", "")))
    out.append(("range:highest", float(hi == gt["highest_midi"]), f"claim {r.get('highest_pitch')} true {gt['highest_midi']}"))
    out.append(("range:lowest", float(lo == gt["lowest_midi"]), f"claim {r.get('lowest_pitch')} true {gt['lowest_midi']}"))
    out.append(("range:active_voice",
                float(str(r.get("most_active_voice", "")).strip().lower() == str(gt["most_active_voice"]).lower()),
                f"claim {r.get('most_active_voice')} true {gt['most_active_voice']}"))
    try:
        span_ok = abs(int(r.get("active_voice_span_semitones", -999)) - gt["active_span"]) <= SPAN_TOL
    except (TypeError, ValueError):
        span_ok = False
    out.append(("range:span", float(span_ok), f"claim {r.get('active_voice_span_semitones')} true {gt['active_span']}"))

    # ---- rhythm-basic ----
    rb = claim.get("rhythm_basic", {})
    try:
        lo_ok = abs(float(rb.get("longest_note_beats", -999)) - gt["longest_beats"]) <= DUR_TOL
    except (TypeError, ValueError):
        lo_ok = False
    out.append(("rhythm_basic:longest", float(lo_ok), f"claim {rb.get('longest_note_beats')} true {gt['longest_beats']}"))
    out.append(("rhythm_basic:over_bar", float(bool(rb.get("any_note_longer_than_bar")) == gt["any_longer_than_bar"]),
                f"claim {rb.get('any_note_longer_than_bar')} true {gt['any_longer_than_bar']}"))
    out.append(("rhythm_basic:densest", float(rb.get("densest_bar") == gt["densest_bar"]),
                f"claim {rb.get('densest_bar')} true {gt['densest_bar']}"))

    # ---- repetition ----
    rep = claim.get("repetition", {})
    if rep.get("none"):
        correct = gt["max_bar_sim"] < NEAR_IDENTICAL_JACCARD
        det = f"claim none; true max_sim {gt['max_bar_sim']:.2f}"
    else:
        a, b = rep.get("bar_a"), rep.get("bar_b")
        sim = bar_similarity(song, a, b) if (a and b) else 0.0
        correct = sim >= NEAR_IDENTICAL_JACCARD
        det = f"claim {a}~{b}; sim {sim:.2f}"
    out.append(("repetition", float(correct), det))

    # ---- voice relations ----
    vr = claim.get("voice_relations", {})
    par = vr.get("parallel", {})
    out.append(("voice_rel:parallel",
                float(_ever_parallel(song, par.get("voice_a"), par.get("voice_b")) == bool(par.get("ever"))),
                f"claim {par.get('ever')} pair {par.get('voice_a')}/{par.get('voice_b')}"))
    iv = vr.get("interval", {})
    out.append(("voice_rel:interval",
                float(_ever_interval(song, iv.get("voice_a"), iv.get("voice_b"), iv.get("semitones")) == bool(iv.get("ever"))),
                f"claim {iv.get('ever')} {iv.get('semitones')}st {iv.get('voice_a')}/{iv.get('voice_b')}"))

    # ---- pitch content ----
    pcq = claim.get("pitch_content", {})
    qpc = parse_pc(str(pcq.get("query_pc", "")))
    present = (qpc in gt["present_pcs"]) if qpc is not None else None
    out.append(("pitch_content:present", float(present == bool(pcq.get("query_pc_present"))),
                f"claim {pcq.get('query_pc')}={pcq.get('query_pc_present')} true {present}"))
    try:
        cnt_ok = int(pcq.get("distinct_pc_count", -1)) == gt["distinct_pc_count"]
    except (TypeError, ValueError):
        cnt_ok = False
    out.append(("pitch_content:count", float(cnt_ok), f"claim {pcq.get('distinct_pc_count')} true {gt['distinct_pc_count']}"))

    # ---- scale / mode ----
    sm = claim.get("scale_mode", {})
    out.append(("scale_mode", _grade_scale(song, sm.get("tonic"), sm.get("mode")),
                f"claim {sm.get('tonic')} {sm.get('mode')}"))

    # ---- rhythm type ----
    rt = claim.get("rhythm_type", {})
    out.append(("rhythm_type:subdivision", float(str(rt.get("subdivision", "")).lower() == gt["subdivision"]),
                f"claim {rt.get('subdivision')} true {gt['subdivision']}"))
    out.append(("rhythm_type:syncopation", float(bool(rt.get("syncopation")) == gt["syncopation"]),
                f"claim {rt.get('syncopation')} true {gt['syncopation']}"))
    out.append(("rhythm_type:note_value",
                float(str(rt.get("predominant_note_value", "")).lower() == str(gt["note_value"]).lower()),
                f"claim {rt.get('predominant_note_value')} true {gt['note_value']}"))

    # ---- chord by constituents (grade the NOTES, not the chord name) ----
    for c in (claim.get("chords") or [])[:CHORD_BARS]:
        bar = c.get("bar")
        asserted = {parse_pc(str(x)) for x in (c.get("pitch_classes") or [])}
        asserted.discard(None)
        present_pcs = song.bar_pcs(bar) if bar else set()
        ok = bool(asserted) and asserted.issubset(present_pcs)
        out.append(("chord_constituents", float(ok),
                    f"bar {bar} asserted {sorted(asserted)} present {sorted(present_pcs)}"))
    return out


def _ever_parallel(song, va, vb):
    if not va or not vb or va not in song.voices or vb not in song.voices:
        return False
    la, lb = song.line(va), song.line(vb)
    shared = sorted(set(la) & set(lb))
    for t1, t2 in zip(shared, shared[1:]):
        da, db = la[t2] - la[t1], lb[t2] - lb[t1]
        if da != 0 and da == db:
            return True
    return False


def _ever_interval(song, va, vb, semis):
    if not va or not vb or semis is None or va not in song.voices or vb not in song.voices:
        return False
    times = sorted({e["abs"] for e in song.voice_events(va)} | {e["abs"] for e in song.voice_events(vb)})
    for t in times:
        A, B = song.sounding_midis(va, t), song.sounding_midis(vb, t)
        for x in A:
            for y in B:
                if abs(x - y) == int(semis):
                    return True
    return False


def _grade_scale(song, tonic, mode):
    pcw = song.pc_weight()
    total = sum(pcw.values())
    if total <= 0 or tonic is None or mode is None:
        return 0.0
    tpc = parse_pc(str(tonic))
    iv = SCALE_INTERVALS.get(str(mode).strip().lower())
    if tpc is None or iv is None:
        return 0.0
    template = {(tpc + i) % 12 for i in iv}
    in_mass = sum(w for pc, w in pcw.items() if pc in template) / total
    if in_mass < SCALE_MASS_THRESH:
        return 0.0
    tonic_est = max(pcw, key=pcw.get)        # note-derived tonic estimate (most pitch-mass)
    return 1.0 if tpc == tonic_est else 0.5  # full if tonic matches, else partial (right notes)


# --------------------------------------------------------------------------- #
# SELF-TEST — proves the grader before any API spend.
# --------------------------------------------------------------------------- #
def self_test():
    files = sorted(GRAMMAR_DIR.glob("song_*.txt"))
    if not files:
        print("No grammar files found.", file=sys.stderr)
        return False
    song = Song(files[0])
    gt = ground_truth(song)
    mav = gt["most_active_voice"]
    print(f"Self-test on {files[0].name}: {len(song.events)} note-events, "
          f"{len(song.voices)} voices, {song.n_bars} bars")
    print(f"  ground truth: highest_midi={gt['highest_midi']} lowest={gt['lowest_midi']} "
          f"active_voice={mav} span={gt['active_span']} longest_beats={gt['longest_beats']} "
          f"densest_bar={gt['densest_bar']} distinct_pc={gt['distinct_pc_count']} "
          f"subdiv={gt['subdivision']} sync={gt['syncopation']} value={gt['note_value']}")

    present_pc = next(iter(gt["present_pcs"]))
    absent_pc = next((p for p in range(12) if p not in gt["present_pcs"]), None)

    # TRUE claim set (built from computed ground truth)
    true_claim = {
        "range": {"highest_pitch": _midi_name(gt["highest_midi"]),
                  "lowest_pitch": _midi_name(gt["lowest_midi"]),
                  "most_active_voice": mav, "active_voice_span_semitones": gt["active_span"]},
        "rhythm_basic": {"longest_note_beats": gt["longest_beats"],
                         "any_note_longer_than_bar": gt["any_longer_than_bar"],
                         "densest_bar": gt["densest_bar"]},
        "repetition": {"none": gt["max_bar_sim"] < NEAR_IDENTICAL_JACCARD, "bar_a": 0, "bar_b": 0},
        "voice_relations": {"parallel": {"voice_a": mav, "voice_b": mav, "ever": True},  # a voice is trivially parallel to itself? no-> handle
                            "interval": {"voice_a": mav, "voice_b": mav, "semitones": 0, "ever": True}},
        "pitch_content": {"query_pc": PC_NAMES[present_pc], "query_pc_present": True,
                          "distinct_pc_count": gt["distinct_pc_count"]},
        "scale_mode": {"tonic": "C", "mode": "chromatic-nonsense"},   # ungradeable mode -> 0 (expected)
        "rhythm_type": {"subdivision": gt["subdivision"], "syncopation": gt["syncopation"],
                        "predominant_note_value": gt["note_value"]},
        "chords": [{"bar": b, "chord": "X", "pitch_classes": [PC_NAMES[p] for p in sorted(song.bar_pcs(b))][:3]}
                   for b in sorted({e["bar"] for e in song.events})[:CHORD_BARS]],
    }
    # find a real near-identical pair if one exists, else assert none
    bars = sorted({e["bar"] for e in song.events})
    pair = None
    for i in range(len(bars)):
        for j in range(i + 1, len(bars)):
            if bar_similarity(song, bars[i], bars[j]) >= NEAR_IDENTICAL_JACCARD:
                pair = (bars[i], bars[j]); break
        if pair:
            break
    if pair:
        true_claim["repetition"] = {"none": False, "bar_a": pair[0], "bar_b": pair[1]}

    # FALSE claim set (deliberately wrong)
    false_claim = {
        "range": {"highest_pitch": _midi_name(gt["highest_midi"] - 5),
                  "lowest_pitch": _midi_name(gt["lowest_midi"] + 5),
                  "most_active_voice": "NotAVoice", "active_voice_span_semitones": gt["active_span"] + 12},
        "rhythm_basic": {"longest_note_beats": gt["longest_beats"] + 3,
                         "any_note_longer_than_bar": not gt["any_longer_than_bar"],
                         "densest_bar": (gt["densest_bar"] % song.n_bars) + 1},
        "repetition": {"none": not (gt["max_bar_sim"] < NEAR_IDENTICAL_JACCARD), "bar_a": 1, "bar_b": 2},
        "voice_relations": {"parallel": {"voice_a": "NotA", "voice_b": "NotB", "ever": True},
                            "interval": {"voice_a": "NotA", "voice_b": "NotB", "semitones": 7, "ever": True}},
        "pitch_content": {"query_pc": (PC_NAMES[absent_pc] if absent_pc is not None else "C"),
                          "query_pc_present": True, "distinct_pc_count": gt["distinct_pc_count"] + 3},
        "scale_mode": {"tonic": "C", "mode": "major"},
        "rhythm_type": {"subdivision": ("triplet" if gt["subdivision"] == "straight" else "straight"),
                        "syncopation": not gt["syncopation"], "predominant_note_value": "whole"},
        "chords": [{"bar": b, "chord": "X",
                    "pitch_classes": [PC_NAMES[(absent_pc if absent_pc is not None else 1)]]}
                   for b in sorted({e["bar"] for e in song.events})[:CHORD_BARS]],
    }

    tg = grade(song, true_claim)
    fg = grade(song, false_claim)
    # expectations: true_claim mostly 1.0 (scale_mode intentionally 0 = unparseable mode);
    #               false_claim mostly 0.0.
    print("\n  TRUE-claim grades (expect ~all 1.0 except scale_mode=0, the deliberate trap):")
    for cat, sc, det in tg:
        print(f"    {sc:.1f}  {cat:<24} {det}")
    print("\n  FALSE-claim grades (expect ~all 0.0; pitch absent_pc may be 0; scale C-major may fit):")
    for cat, sc, det in fg:
        print(f"    {sc:.1f}  {cat:<24} {det}")

    true_nonscale = [sc for cat, sc, _ in tg if cat != "scale_mode"]
    false_score = [sc for cat, sc, _ in fg]
    t_ok = sum(true_nonscale) / len(true_nonscale)
    f_ok = sum(false_score) / len(false_score)
    print(f"\n  TRUE-claim mean (excl. scale trap): {t_ok:.2f}  (want high, ~1.0)")
    print(f"  FALSE-claim mean:                   {f_ok:.2f}  (want low)")
    ok = t_ok >= 0.85 and f_ok <= 0.30
    print(f"  GRADER SELF-TEST: {'PASS' if ok else 'FAIL'}")
    return ok


def _midi_name(m):
    if m is None:
        return "C4"
    return f"{PC_NAMES[m % 12]}{m // 12 - 1}"


# --------------------------------------------------------------------------- #
# Neural elicitation + full probe.
# --------------------------------------------------------------------------- #
CLAIM_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "range": {"type": "object", "additionalProperties": False, "properties": {
            "highest_pitch": {"type": "string"}, "lowest_pitch": {"type": "string"},
            "most_active_voice": {"type": "string"}, "active_voice_span_semitones": {"type": "integer"}},
            "required": ["highest_pitch", "lowest_pitch", "most_active_voice", "active_voice_span_semitones"]},
        "rhythm_basic": {"type": "object", "additionalProperties": False, "properties": {
            "longest_note_beats": {"type": "number"}, "any_note_longer_than_bar": {"type": "boolean"},
            "densest_bar": {"type": "integer"}},
            "required": ["longest_note_beats", "any_note_longer_than_bar", "densest_bar"]},
        "repetition": {"type": "object", "additionalProperties": False, "properties": {
            "none": {"type": "boolean"}, "bar_a": {"type": "integer"}, "bar_b": {"type": "integer"}},
            "required": ["none", "bar_a", "bar_b"]},
        "voice_relations": {"type": "object", "additionalProperties": False, "properties": {
            "parallel": {"type": "object", "additionalProperties": False, "properties": {
                "voice_a": {"type": "string"}, "voice_b": {"type": "string"}, "ever": {"type": "boolean"}},
                "required": ["voice_a", "voice_b", "ever"]},
            "interval": {"type": "object", "additionalProperties": False, "properties": {
                "voice_a": {"type": "string"}, "voice_b": {"type": "string"},
                "semitones": {"type": "integer"}, "ever": {"type": "boolean"}},
                "required": ["voice_a", "voice_b", "semitones", "ever"]}},
            "required": ["parallel", "interval"]},
        "pitch_content": {"type": "object", "additionalProperties": False, "properties": {
            "query_pc": {"type": "string"}, "query_pc_present": {"type": "boolean"},
            "distinct_pc_count": {"type": "integer"}},
            "required": ["query_pc", "query_pc_present", "distinct_pc_count"]},
        "scale_mode": {"type": "object", "additionalProperties": False, "properties": {
            "tonic": {"type": "string"}, "mode": {"type": "string"}}, "required": ["tonic", "mode"]},
        "rhythm_type": {"type": "object", "additionalProperties": False, "properties": {
            "subdivision": {"type": "string"}, "syncopation": {"type": "boolean"},
            "predominant_note_value": {"type": "string"}},
            "required": ["subdivision", "syncopation", "predominant_note_value"]},
        "chords": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
            "bar": {"type": "integer"}, "chord": {"type": "string"},
            "pitch_classes": {"type": "array", "items": {"type": "string"}}},
            "required": ["bar", "chord", "pitch_classes"]}},
    },
    "required": ["range", "rhythm_basic", "repetition", "voice_relations", "pitch_content",
                 "scale_mode", "rhythm_type", "chords"],
}

SYSTEM = f"""You are analyzing a blind text score (one bar per @N line; note tokens are
Pitch@onset>duration where onset is a 1-indexed slot within the bar and duration is in
slots; A+C#5+E4 means simultaneous notes; per-bar (grid:G) means that bar uses G slots per
whole note, else the header GRID default). Make SPECIFIC, FALSIFIABLE factual claims that
can be checked exactly against the notes. No hedging, no prose. Use these exact operational
definitions:
- highest/lowest pitch: across ALL voices, scientific names (e.g. C#5).
- most active voice: the voice with the most onset events; active_voice_span_semitones:
  (max-min) semitone span of THAT voice.
- longest_note_beats: longest single note duration in quarter-note beats.
- densest_bar: the bar with the most note events.
- repetition: name two near-identical bars (>=90% of note events shared), or set none=true.
- voice parallel: two voices 'move in parallel' if between two consecutive times where BOTH
  have an onset, their top pitches change by the SAME nonzero number of semitones.
- voice interval ever: at some moment both voices sound pitches exactly `semitones` apart.
- query_pc_present: whether a pitch class you name occurs anywhere; distinct_pc_count: how
  many of the 12 pitch classes occur.
- scale_mode: the scale/mode the notes fit (tonic + mode name like major/minor/dorian/...).
- subdivision: 'straight' or 'triplet' (predominant onset grid); syncopation: true/false
  (>=15% of onsets fall off the beat); predominant_note_value: whole/half/quarter/eighth/
  sixteenth/eighth triplet/etc.
- chords: for {CHORD_BARS} specific bars, give the chord name AND its constituent pitch
  classes (these must be pitch classes that actually sound in that bar).
Pick targets you are CONFIDENT are correct; you are graded only on exactness."""


def _one_pass(client, grammar_text):
    resp = client.messages.create(
        model=NEURAL_MODEL, max_tokens=NEURAL_MAX_TOKENS,
        thinking={"type": "adaptive"},
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": CLAIM_SCHEMA}},
        system=SYSTEM,
        messages=[{"role": "user", "content": grammar_text
                   + f"\n\nReturn the JSON object. Use exactly {CHORD_BARS} entries in 'chords'."}],
    )
    return json.loads(next(b.text for b in resp.content if b.type == "text"))


def elicit(client, grammar_text):
    for attempt in range(2):
        try:
            return _one_pass(client, grammar_text)
        except Exception as e:  # noqa: BLE001
            err = str(e)[:120]
    print(f"    [neural-failed] {err}", file=sys.stderr)
    return None


def report_from_claims(claims_by_sid, source_note):
    """Grade pre-generated claims (e.g. from a CC sub-agent) with the SAME verified grader,
    and print the per-category / baseline / fame report. No API involved."""
    files = sorted(GRAMMAR_DIR.glob("song_*.txt"))
    songs = {f.stem: Song(f) for f in files}
    truths = [ground_truth(s) for s in songs.values()]
    base = baselines(truths)
    base["scale_mode"] = sum(_grade_scale(s, "C", "major") > 0 for s in songs.values()) / len(songs)

    cat_scores = defaultdict(list)
    per_song_acc = {}
    missing = []
    for sid, song in songs.items():
        claim = claims_by_sid.get(sid)
        if claim is None:
            missing.append(sid)
            continue
        graded = grade(song, claim)
        for cat, sc, _ in graded:
            cat_scores[cat].append(sc)
        per_song_acc[sid] = sum(sc for _, sc, _ in graded) / len(graded)

    print("\n" + "=" * 90)
    print("PER-CATEGORY ACCURACY vs NAIVE BASELINE  (the real finding)")
    print(f"claims source: {source_note}")
    print("=" * 90)
    print(f"  {'category':<26}{'model':>8}{'baseline':>10}{'lift':>8}{'n':>6}")
    order = ["range:highest", "range:lowest", "range:active_voice", "range:span",
             "rhythm_basic:longest", "rhythm_basic:over_bar", "rhythm_basic:densest",
             "repetition", "voice_rel:parallel", "voice_rel:interval",
             "pitch_content:present", "pitch_content:count", "scale_mode",
             "rhythm_type:subdivision", "rhythm_type:syncopation", "rhythm_type:note_value",
             "chord_constituents"]
    allm = []
    for cat in order:
        sc = cat_scores.get(cat, [])
        if not sc:
            continue
        m = sum(sc) / len(sc)
        b = base.get(cat, 0.5)
        allm += sc
        print(f"  {cat:<26}{m:>8.2f}{b:>10.2f}{m-b:>+8.2f}{len(sc):>6}")
    overall = sum(allm) / len(allm) if allm else 0
    print(f"  {'OVERALL':<26}{overall:>8.2f}")
    print(f"  graded songs: {len(per_song_acc)}/{len(songs)}"
          + (f"   missing: {missing}" if missing else ""))

    truth = json.loads(ANSWER_KEY.read_text(encoding="utf-8")) if ANSWER_KEY.exists() else {}
    FAMOUS = {"The Beatles", "Queen", "ABBA", "Michael Jackson", "Stevie Wonder", "Elton John",
              "Billy Joel", "Eagles", "Fleetwood Mac", "Simon & Garfunkel", "The Beach Boys",
              "Bee Gees", "Earth, Wind & Fire", "Steely Dan", "Pink Floyd", "Led Zeppelin", "U2",
              "The Police", "Toto", "Chicago", "Journey", "Supertramp", "Prince", "Madonna",
              "Whitney Houston", "Carpenters", "Bob Dylan", "The Rolling Stones", "Boston",
              "The Four Seasons", "Frank Sinatra"}
    fam, obs = [], []
    for sid, acc in per_song_acc.items():
        artist = truth.get(sid, {}).get("artist", "")
        (fam if artist in FAMOUS else obs).append(acc)
    print("\n" + "=" * 90)
    print("MEMORIZATION CONTROL (identity loaded only now, by the grader, only to label)")
    print("=" * 90)
    fa = sum(fam) / len(fam) if fam else 0
    oa = sum(obs) / len(obs) if obs else 0
    print(f"  famous songs (n={len(fam)}):            mean acc {fa:.3f}")
    print(f"  obscure/generated songs (n={len(obs)}): mean acc {oa:.3f}")
    print(f"  gap (famous - obscure): {fa-oa:+.3f}")
    print("  Interpretation: flat across fame => UNDERSTANDING; high-on-famous-only => MEMORIZATION.")
    return 0


def main():
    # Offline mode: grade pre-generated claim JSONs (e.g. from a CC sub-agent).
    if "--grade-dir" in sys.argv:
        cdir = Path(sys.argv[sys.argv.index("--grade-dir") + 1])
        print("=" * 90)
        print("STEP 1 — GRADER SELF-TEST (pure Python, no API)")
        print("=" * 90)
        if not self_test():
            print("\nGrader self-test FAILED — not proceeding.", file=sys.stderr)
            return 1
        claims = {}
        for jf in sorted(cdir.glob("song_*.json")):
            try:
                claims[jf.stem] = json.loads(jf.read_text(encoding="utf-8"))
            except Exception as e:  # noqa: BLE001
                print(f"  [skip unreadable] {jf.name}: {e}", file=sys.stderr)
        return report_from_claims(claims, source_note=f"{cdir}/  ({len(claims)} files)")

    print("=" * 90)
    print("STEP 1 — GRADER SELF-TEST (pure Python, no API)")
    print("=" * 90)
    ok = self_test()
    if not ok:
        print("\nGrader self-test FAILED — not proceeding.", file=sys.stderr)
        return 1

    # API credential?
    client = None
    try:
        import anthropic
        client = anthropic.Anthropic()
        client.with_options(max_retries=0)  # we manage retries
        # cheap probe of credential presence without a full call:
        import os
        if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            raise RuntimeError("no credential in environment")
    except Exception as e:  # noqa: BLE001
        print("\n" + "=" * 90)
        print(f"No API credential ({str(e)[:80]}). Grader is READY and verified.")
        print("Set ANTHROPIC_API_KEY and re-run to execute the full probe.")
        print("=" * 90)
        return 0

    print("\n" + "=" * 90)
    print(f"STEP 2 — FULL PROBE  (model={NEURAL_MODEL})")
    print("=" * 90)
    files = sorted(GRAMMAR_DIR.glob("song_*.txt"))
    songs = {f.stem: Song(f) for f in files}
    truths = [ground_truth(s) for s in songs.values()]
    base = baselines(truths)
    # scale baseline: fraction of songs whose notes fit a fixed 'C major'
    base["scale_mode"] = sum(_grade_scale(s, "C", "major") > 0 for s in songs.values()) / len(songs)

    cat_scores = defaultdict(list)         # category -> [scores]
    per_song_acc = {}                      # sid -> mean accuracy
    neural_failed = []
    for f in files:
        sid = f.stem
        claim = elicit(client, f.read_text(encoding="utf-8"))
        if claim is None:
            neural_failed.append(sid)
            continue
        graded = grade(songs[sid], claim)
        for cat, sc, _ in graded:
            cat_scores[cat].append(sc)
        per_song_acc[sid] = sum(sc for _, sc, _ in graded) / len(graded)
        print(f"  {sid}: {len(graded)} claims, acc {per_song_acc[sid]:.2f}")

    # ---- report ----
    print("\n" + "=" * 90)
    print("PER-CATEGORY ACCURACY vs NAIVE BASELINE  (the real finding)")
    print("=" * 90)
    print(f"  {'category':<26}{'model':>8}{'baseline':>10}{'lift':>8}{'n':>6}")
    order = ["range:highest", "range:lowest", "range:active_voice", "range:span",
             "rhythm_basic:longest", "rhythm_basic:over_bar", "rhythm_basic:densest",
             "repetition", "voice_rel:parallel", "voice_rel:interval",
             "pitch_content:present", "pitch_content:count", "scale_mode",
             "rhythm_type:subdivision", "rhythm_type:syncopation", "rhythm_type:note_value",
             "chord_constituents"]
    allm = []
    for cat in order:
        sc = cat_scores.get(cat, [])
        if not sc:
            continue
        m = sum(sc) / len(sc)
        b = base.get(cat, 0.5)
        allm += sc
        print(f"  {cat:<26}{m:>8.2f}{b:>10.2f}{m-b:>+8.2f}{len(sc):>6}")
    overall = sum(allm) / len(allm) if allm else 0
    print(f"  {'OVERALL':<26}{overall:>8.2f}")
    if neural_failed:
        print(f"  (neural-failed, excluded: {neural_failed})")

    # ---- memorization control ----
    truth = json.loads(ANSWER_KEY.read_text(encoding="utf-8")) if ANSWER_KEY.exists() else {}
    FAMOUS = {"The Beatles", "Queen", "ABBA", "Michael Jackson", "Stevie Wonder", "Elton John",
              "Billy Joel", "Eagles", "Fleetwood Mac", "Simon & Garfunkel", "The Beach Boys",
              "Bee Gees", "Earth, Wind & Fire", "Steely Dan", "Pink Floyd", "Led Zeppelin", "U2",
              "The Police", "Toto", "Chicago", "Journey", "Supertramp", "Prince", "Madonna",
              "Whitney Houston", "Carpenters", "Bob Dylan", "The Rolling Stones", "Boston",
              "The Four Seasons", "Frank Sinatra"}
    fam, obs = [], []
    for sid, acc in per_song_acc.items():
        artist = truth.get(sid, {}).get("artist", "")
        (fam if artist in FAMOUS else obs).append(acc)
    print("\n" + "=" * 90)
    print("MEMORIZATION CONTROL (identity loaded only now, only to label)")
    print("=" * 90)
    fa = sum(fam) / len(fam) if fam else 0
    oa = sum(obs) / len(obs) if obs else 0
    print(f"  famous songs (n={len(fam)}):           mean acc {fa:.3f}")
    print(f"  obscure/generated songs (n={len(obs)}): mean acc {oa:.3f}")
    print(f"  gap (famous - obscure): {fa-oa:+.3f}")
    print("  Interpretation: flat across fame => UNDERSTANDING; high-on-famous-only => MEMORIZATION.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
