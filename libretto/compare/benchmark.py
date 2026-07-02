"""libretto.compare.benchmark — a reproducible, tool-free ABC-vs-Libretto reading benchmark.

Same music, two encodings; only onset representation differs (ABC = relative durations / running prefix-sum,
Libretto = absolute slot). Every stimulus is emitted in BOTH notations from one event list, with objective
questions + computed ground truth, so an LLM reader can be scored by musical identity. The LLM *run* is external
(feed the prompts to any tool-free reader); everything reproducible — stimuli, questions, ground truth, scorer,
and a hallucination (out-of-meter) metric — lives here and is self-validated by `oracle()`.

Tasks (see `TASKS`): T1 onset-recovery, T2 vertical-alignment, T3 chord-at-slot, T4 voice-leading,
T5 copy-risk overlap, T6 edit blast-radius, T7 timing-drift. Plus `build_hallucination()` — dense/deep passages
meant for a quick-read prompt, where ABC over-accumulation yields impossible beats and Libretto cannot.

Quick start
-----------
    from libretto.compare import benchmark as B
    items = B.build(B.HIGH_SIGNAL, seeds=(0, 1))     # stimuli + questions + ground truth
    ok, _ = B.oracle(items)                          # self-check: ground truth scores 100%
    ap, lp = B.prompts(items[0])                     # the two tool-free reader prompts
    B.score_one(items[0]["qs"][0]["type"], "bar 2 beat 3", items[0]["qs"][0]["gt"], "abc")
"""
import random
import re
from collections import defaultdict

from .abc import emit_abc, emit_libretto, sci

# ---------------------------------------------------------------- task registry + presets
TASKS = {
    "T1": "onset recovery — beat of a marked note",
    "T2": "vertical alignment — what sounds in each voice at a beat",
    "T3": "chord at a slot — the sounding pitch-set",
    "T4": "voice-leading — signed interval each voice moves between two beats",
    "T5": "copy-risk — count identical (beat,pitch) between two bars",
    "T6": "edit blast-radius — the final note's beat after one duration edit",
    "T7": "timing drift — which bar no longer fills 4/4",
}
HIGH_SIGNAL = {"T1": [2, 8], "T4": [2, 4], "T6": [2, 8]}   # accumulation/reconstruction-heavy, clear signatures
FULL = {"T1": [1, 2, 4, 8], "T2": [2, 3, 4], "T3": [2, 3, 4], "T4": [2, 3, 4],
        "T5": [2, 4, 8], "T6": [1, 2, 4, 8], "T7": [2, 4, 8]}

SCALE_C = [60, 62, 64, 65, 67, 69, 71, 72, 74, 76, 77, 79]           # C-major, C4..G5
VOICES = {2: ["RH", "LH"], 3: ["S", "A", "B"], 4: ["S", "A", "T", "B"]}
BASE = {"RH": 72, "LH": 48, "S": 74, "A": 65, "T": 55, "B": 45, "M": 67}


# ---------------------------------------------------------------- music generation
def _compose_bar(rng, dense=False):
    parts, rem = [], 8
    pool = (1, 1, 1, 2, 2, 3) if dense else (1, 2, 3, 4)
    while rem:
        p = rng.choice([x for x in pool if x <= rem])
        parts.append(p * 0.5); rem -= p
    return parts


def _walk(rng, base, n):
    i = min(range(len(SCALE_C)), key=lambda k: abs(SCALE_C[k] - base))
    out = []
    for _ in range(n):
        i = max(0, min(len(SCALE_C) - 1, i + rng.choice([-2, -1, -1, 1, 1, 2])))
        out.append(SCALE_C[i])
    return out


def _gen_voice(rng, voice, bars, dense=False):
    ev, onset = [], 0.0
    for _ in range(bars):
        durs = _compose_bar(rng, dense)
        for d, m in zip(durs, _walk(rng, BASE[voice], len(durs))):
            ev.append([voice, round(onset, 3), d, m]); onset += d
    return ev


def _gen_mono(seed, bars, dense=False):
    return _gen_voice(random.Random(seed), "M", bars, dense)


def _gen_poly(seed, nv, bars):
    rng = random.Random(seed)
    return [e for v in VOICES[nv] for e in _gen_voice(rng, v, bars)]


# ---------------------------------------------------------------- shared helpers
def loc(onset):
    bar = int(onset // 4) + 1
    return bar, onset - (bar - 1) * 4 + 1


def loc_str(onset):
    b, bt = loc(onset)
    return f"bar {b} beat {bt:g}"


def _sounding(ev, voice, x):
    hit = None
    for v, o, d, m in ev:
        if v == voice and o <= x + 1e-9 < o + d - 1e-9:
            hit = m
    return hit


# ---------------------------------------------------------------- item builders
def build(spec=None, seeds=(0, 1)):
    """Build benchmark items for tasks per `spec` = {task: [scales]} (default HIGH_SIGNAL).

    Each item: dict(id, task, scale, seed, voices, bars, abc, lib, qs=[dict(qid,type,q,gt)]).
    """
    spec = spec or HIGH_SIGNAL
    items = []

    def add(task, scale, seed, ev, voices, bars, qs, marks=frozenset(), abc=None, lib=None):
        items.append(dict(id=f"{task}_s{scale}_r{seed}", task=task, scale=scale, seed=seed,
                          voices=voices, bars=bars,
                          abc=abc if abc is not None else emit_abc(ev, voices, bars, marks),
                          lib=lib if lib is not None else emit_libretto(ev, voices, bars, marks), qs=qs))

    for seed in seeds:
        for bars in spec.get("T1", []):
            ev = _gen_mono(seed, bars)
            last = [e for e in ev if int(e[1] // 4) == bars - 1]
            mk = last[1] if len(last) > 1 else last[0]
            add("T1", bars, seed, ev, ["M"], bars, [dict(qid="Q1", type="onset",
                q="At what bar and beat does the note marked * begin? Answer 'bar B beat X'.",
                gt=loc_str(mk[1]))], {(mk[0], round(mk[1], 3))})

        for bars in spec.get("T5", []):
            rng = random.Random(1000 + seed)
            ev = _gen_mono(seed, bars)
            b1 = [e for e in ev if int(e[1] // 4) == 0]
            ev = [e for e in ev if int(e[1] // 4) != 1]
            changed = 0
            for v, o, d, m in b1:
                nm = m
                if rng.random() < 0.35:
                    nm = rng.choice([p for p in SCALE_C if p != m]); changed += 1
                ev.append([v, round(o + 4, 3), d, nm])
            ev.sort(key=lambda e: e[1])
            add("T5", bars, seed, ev, ["M"], bars, [dict(qid="Q1", type="count",
                q="How many notes have the SAME within-bar beat position AND the same pitch in both bar 1 and "
                  "bar 2? Answer a single integer.", gt=len(b1) - changed)])

        for bars in spec.get("T6", []):
            ev = _gen_mono(seed, bars)
            if len(ev) < 3:
                continue
            mk, last = ev[1], ev[-1]
            add("T6", bars, seed, ev, ["M"], bars, [dict(qid="Q1", type="onset",
                q="You lengthen the note marked * by one eighth note (0.5 beat), editing ONLY that token's own "
                  "written duration and changing no other token. After this edit, at what bar and beat does the "
                  "FINAL note of the passage begin? Answer 'bar B beat X'.",
                gt={"abc": loc_str(last[1] + 0.5), "lib": loc_str(last[1])})], {(mk[0], round(mk[1], 3))})

        for bars in spec.get("T7", []):
            rng = random.Random(2000 + seed)
            ev = _gen_mono(seed, bars)
            dbar = rng.randrange(bars)
            tgt = sorted([e for e in ev if int(e[1] // 4) == dbar], key=lambda e: e[1])[-1]
            for e in ev:
                if e is tgt:
                    e[2] = round(e[2] - 0.5, 3)
            add("T7", bars, seed, ev, ["M"], bars, [dict(qid="Q1", type="bar",
                q="Exactly one bar has been mis-edited so its contents no longer fill a full 4/4 measure (they "
                  "sum to less than 4 beats). Which bar? Answer 'bar B'.", gt=dbar + 1)])

        for nv in sorted(set(spec.get("T2", []) + spec.get("T3", []) + spec.get("T4", []))):
            bars = 2
            ev, voices = _gen_poly(seed, nv, bars), VOICES[nv]
            x0, x1, x2 = 1.5, 1.5, bars * 4 - 2.5
            snd0 = {v: _sounding(ev, v, x0) for v in voices}
            b0, bt0 = loc(x0)
            if nv in spec.get("T2", []):
                add("T2", nv, seed, ev, voices, bars, [dict(qid="Q1", type="pitch_each",
                    q=f"At bar {b0} beat {bt0:g}, what note is sounding in EACH voice ({', '.join(voices)})? "
                      f"Answer 'V:pitch' per voice, comma-separated (scientific pitch, e.g. C4).",
                    gt={v: sci(snd0[v]) for v in voices})])
            if nv in spec.get("T3", []):
                add("T3", nv, seed, ev, voices, bars, [dict(qid="Q1", type="pcset",
                    q=f"At bar {b0} beat {bt0:g}, list the SET of all pitches sounding across every voice "
                      f"(pitch letters, any octave). Answer the pitches separated by spaces.",
                    gt=sorted({snd0[v] % 12 for v in voices}))])
            if nv in spec.get("T4", []):
                sa = {v: _sounding(ev, v, x1) for v in voices}
                sb = {v: _sounding(ev, v, x2) for v in voices}
                ba, bta = loc(x1); bb, btb = loc(x2)
                add("T4", nv, seed, ev, voices, bars, [dict(qid="Q1", type="intervals",
                    q=f"For each voice ({', '.join(voices)}), the pitch sounding at bar {ba} beat {bta:g} moves "
                      f"to the pitch sounding at bar {bb} beat {btb:g}. Give each voice's motion in signed "
                      f"semitones (up +, down -). Answer 'V:+n' per voice, comma-separated.",
                    gt={v: sb[v] - sa[v] for v in voices})])
    return items


def build_hallucination(seeds=range(6), scales=(8, 12)):
    """Dense, deep T1 items with the marked note = LAST note of the final bar (max within-bar accumulation).
    Meant for a QUICK-READ prompt (`prompts(item, quick=True)`): provokes ABC out-of-meter answers."""
    items = []
    for seed in seeds:
        for bars in scales:
            ev = _gen_mono(seed, bars, dense=True)
            mk = ev[-1]
            items.append(dict(id=f"H_s{bars}_r{seed}", task="T1", scale=bars, seed=seed, voices=["M"], bars=bars,
                              abc=emit_abc(ev, ["M"], bars, {(mk[0], round(mk[1], 3))}),
                              lib=emit_libretto(ev, ["M"], bars, {(mk[0], round(mk[1], 3))}),
                              qs=[dict(qid="Q1", type="onset",
                                       q="At what bar and beat does the note marked * begin? Answer 'bar B beat X'.",
                                       gt=loc_str(mk[1]))]))
    return items


# ---------------------------------------------------------------- prompts
LEGEND_ABC = ("You are reading music in ABC notation. Header: M:4/4 (4 beats/bar), L:1/8 (a plain letter = one "
              "eighth = half a beat; a trailing number multiplies, so C2 = a quarter = 1 beat, C4 = a half = 2 "
              "beats, C3 = dotted quarter = 1.5 beats). Uppercase C..B = octave 4 (C = C4); lowercase = octave 5; "
              "a comma lowers an octave (C, = C3), an apostrophe raises one. 'z' = rest. '|' = barline. "
              "[V:x] labels a voice. Beats within a bar are counted from 1.")
LEGEND_LIB = ("You are reading music in Libretto grammar. GRID: 16th means each bar has 16 slots; beats fall on "
              "slots 1, 5, 9, 13 (beat = (slot-1)/4 + 1, so slot 3 = beat 1.5, slot 7 = beat 2.5). A token "
              "'P@s>d' is pitch P starting AT slot s for d slots (scientific pitch, e.g. C4). '@n [chord]' heads "
              "bar n. Each indented line is one voice.")
RULE = ("Answer by READING ONLY — do not write or run any code. Give exactly one line per question in the form "
        "'Qid: <answer>' and nothing else.")
QUICK = ("Answer IMMEDIATELY from a single quick read. Do NOT write out any steps, counting, or working — output "
         "ONLY the one line 'Qid: <answer>' and nothing else.")


def prompts(item, quick=False):
    """Return (abc_prompt, lib_prompt) for a tool-free reader. `quick=True` = no-scratchpad (hallucination mode)."""
    rule = QUICK if quick else RULE
    q = "\n".join(f"{x['qid']}: {x['q']}" for x in item["qs"])
    out = []
    for enc, legend in ((item["abc"], LEGEND_ABC), (item["lib"], LEGEND_LIB)):
        out.append(f"{legend}\n\n{rule}\n\n--- SCORE ---\n{enc}\n--- END ---\n\nQUESTIONS:\n{q}\n")
    return tuple(out)


# ---------------------------------------------------------------- scoring (by musical identity)
_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_ONSET_TASKS = {"onset", "bar"}
_VP = re.compile(r"([A-Za-z]+)\s*[:=]\s*([+-]?[A-Ga-g#b,'\d]+)")


def _pitch(tok):
    """(pitch-class, octave) from scientific (C4) OR ABC letters (uppercase=oct4, lowercase=oct5, ,/' shift)."""
    m = re.match(r"^\*?([A-Ga-g])([#b]?)([,']*)(\d?)$", tok.strip())
    if not m:
        return None
    let, _acc, marks, digit = m.groups()
    if let.isupper() and not marks and digit:
        return (_PC[let.upper()], int(digit))
    return (_PC[let.upper()], (4 if let.isupper() else 5) + marks.count("'") - marks.count(","))


def _onset(s):
    m = re.search(r"bar\s*(\d+)\s*beat\s*([\d.]+)", s, re.I)
    return (int(m.group(1)), float(m.group(2))) if m else None


def _voice_map(s):
    out = {}
    for part in re.split(r",\s+", s):                       # ABC octave commas never precede a space
        m = _VP.search(part)
        if m:
            out[m.group(1).upper()] = m.group(2)
    return out


def score_one(qtype, answer, gt, cond):
    """True iff `answer` matches ground truth `gt` for a question of `qtype` in condition `cond` ('abc'|'lib')."""
    if isinstance(gt, dict) and set(gt) == {"abc", "lib"}:      # representation-specific truth (T6)
        gt = gt[cond]
    if qtype == "onset":
        return _onset(answer) == _onset(gt)
    if qtype == "bar":
        m = re.search(r"bar\s*(\d+)", answer, re.I) or re.search(r"\b(\d+)\b", answer)
        return bool(m) and int(m.group(1)) == int(gt)
    if qtype == "count":
        m = re.search(r"-?\d+", answer)
        return bool(m) and int(m.group()) == int(gt)
    if qtype == "pitch_each":
        got = _voice_map(answer)
        return bool(gt) and all(_pitch(got.get(v, "")) == _pitch(p) for v, p in gt.items())
    if qtype == "pcset":
        got = {(_pitch(t) or (None,))[0] for t in re.findall(r"[A-Ga-g][#b]?[,']*\d?", answer)} - {None}
        return got == set(gt)
    if qtype == "intervals":
        got = _voice_map(answer)
        try:
            return bool(gt) and all(int(got.get(v, "x")) == int(n) for v, n in gt.items())
        except ValueError:
            return False
    return False


def impossible(item, qtype, answer):
    """Hallucination check for the pure-read task T1: an answer naming a position that CANNOT exist (beat outside
    1..4.5, or a bar past the passage). None if not checkable/unparseable. Libretto readers cannot produce one —
    an absolute slot maps to a beat inside its bar by construction. (T6 excluded: its ABC truth may overflow.)"""
    if item["task"] == "T1" and qtype == "onset":
        o = _onset(answer)
        if not o:
            return None
        bar, beat = o
        return not (1 <= bar <= item["bars"] and 1 <= beat <= 4.5)
    return None


def gt_answer(qtype, gt, cond):
    """A canonical correct answer string for `gt` (used by `oracle`)."""
    if isinstance(gt, dict) and set(gt) == {"abc", "lib"}:
        gt = gt[cond]
    if qtype in ("onset",):
        return gt
    if qtype == "bar":
        return f"bar {gt}"
    if qtype == "count":
        return str(gt)
    if qtype == "pitch_each":
        return ", ".join(f"{v}:{p}" for v, p in gt.items())
    if qtype == "pcset":
        names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        return " ".join(sorted({names[p] for p in gt}))
    if qtype == "intervals":
        return ", ".join(f"{v}:{n:+d}" for v, n in gt.items())
    return ""


def parse_answers(text):
    """Parse a reader's reply ('Qid: <answer>' lines) into {qid: answer}."""
    out = {}
    for line in text.splitlines():
        m = re.match(r"\s*(Q\d+)\s*:\s*(.+)", line)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def oracle(items):
    """Score ground truth against itself. Returns (ok: bool, detail: dict). ok requires 100% and 0 impossible."""
    correct = total = imp = 0
    for it in items:
        for cond in ("abc", "lib"):
            for q in it["qs"]:
                a = gt_answer(q["type"], q["gt"], cond)
                total += 1
                correct += score_one(q["type"], a, q["gt"], cond)
                if impossible(it, q["type"], a):
                    imp += 1
    return (correct == total and imp == 0), dict(correct=correct, total=total, impossible=imp)


def summarize(items, answers, quick=False):
    """Score a dict `answers` = {item_id: {'abc': reply_text, 'lib': reply_text}} and aggregate by condition.

    Returns dict with per-condition accuracy and (for T1) impossible-answer rate.
    """
    acc = defaultdict(lambda: [0, 0]); hall = defaultdict(lambda: [0, 0])
    for it in items:
        for cond in ("abc", "lib"):
            reply = (answers.get(it["id"], {}) or {}).get(cond)
            if reply is None:
                continue
            parsed = parse_answers(reply)
            for q in it["qs"]:
                a = parsed.get(q["qid"], "")
                acc[cond][1] += 1; acc[cond][0] += score_one(q["type"], a, q["gt"], cond)
                im = impossible(it, q["type"], a)
                if im is not None:
                    hall[cond][1] += 1; hall[cond][0] += im
    return {c: dict(accuracy=(acc[c][0], acc[c][1]),
                    impossible=(hall[c][0], hall[c][1])) for c in ("abc", "lib")}
