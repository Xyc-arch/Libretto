#!/usr/bin/env python3
"""inject — PURE anomaly injectors for the anomaly-detection task.

Every function takes grammar TEXT and returns (new_text, anomaly_meta) WITHOUT mutating the input — the source
corpus is never touched; callers write the returned copy to a separate cases dir. Each injector makes ONE
subtle, music-tradition-violating change to ONE bar and reports its location + type as ground truth. Target
selection is deterministic given `seed`, so cases are reproducible.

Anomalies:
  out_of_key      — shift one melody note ±1 semitone to a pitch OUTSIDE the key (a wrong note)
  wrong_bass      — move a bar's bass note to a wrong root (breaks the harmony's foundation)
  dissonance      — add a semitone-clash tone to a chord (a harsh non-chord tone)
  meter_glitch    — extend one note so the bar overflows its beat grid (a dropped/added beat)
  voice_crossing  — raise a lower voice above a higher one at the same time (parts cross)
  parallel_fifths — force two voices into consecutive parallel perfect fifths (counterpoint fault)
Voice-leading kinds exclude drum voices (percussion is not pitched).
"""
import random
import re

import pretty_midi as pm

from libretto.tasks.education.measure import scale_pcs

# a note token: pitchspec@slot>dur(^vel)? ; pitchspec = one or more note-names joined by '+'
_NOTE = r"[A-G][#b]?-?\d+"
_TOK = re.compile(rf"((?:{_NOTE})(?:\+{_NOTE})*)@(\d+)>(\d+)(\^\d+)?")


def _midi(nn):
    try:
        return pm.note_name_to_number(nn)
    except Exception:
        return None


def _name(m):
    return pm.note_number_to_name(m)


def _split(text):
    """(head_lines, bars) where each bar = [marker_line, voice_line, ...]. Pure."""
    head, bars, cur = [], [], None
    for ln in text.splitlines():
        if ln.startswith("@"):
            if cur is not None:
                bars.append(cur)
            cur = [ln]
        elif cur is None:
            head.append(ln)
        else:
            cur.append(ln)
    if cur is not None:
        bars.append(cur)
    return head, bars


def _join(head, bars):
    out = list(head)
    for b in bars:
        out.extend(b)
    return "\n".join(out) + "\n"


def _voice(line):
    return line.partition(":")[0].strip()


def _key_from_header(text):
    m = re.search(r"KEY:\s*([^|]+)", text)
    return m.group(1).strip() if m else "C major"


def _interior_bars(bars, seed=0, margin=2):
    """Bar indices with >=1 voice line, avoiding the first/last `margin` (anomaly not at the edges), in a
    seed-shuffled order so different seeds inject into DIFFERENT bars (varied, reproducible cases)."""
    idx = [i for i, b in enumerate(bars) if any(":" in ln for ln in b[1:])]
    interior = [i for i in idx if margin <= i < len(bars) - margin] or idx
    random.Random(seed).shuffle(interior)
    return interior


def _pick(seq, seed, salt=0):
    return random.Random((seed, salt)).choice(seq) if seq else None


def _replace_first_tok(line, fn):
    """Apply fn(pitchspec, slot, dur, vel) -> new_pitchspec (or None to skip) to the FIRST token it edits.
    Preserves slot/dur/vel and the rest of the line exactly. Returns (new_line, edited_bool, detail)."""
    edited = {"done": False, "detail": None}

    def _sub(mm):
        if edited["done"]:
            return mm.group(0)
        ps, slot, dur, vel = mm.group(1), mm.group(2), mm.group(3), mm.group(4) or ""
        new = fn(ps, int(slot), int(dur), vel)
        if new is None:
            return mm.group(0)
        edited["done"] = True
        edited["detail"] = (ps, new)
        return f"{new}@{slot}>{dur}{vel}"

    return _TOK.sub(_sub, line), edited["done"], edited["detail"]


# ── injectors (each: text, seed -> (new_text, meta) or (None, None) if no suitable site) ─────────────────
def out_of_key(text, seed=0):
    key = _key_from_header(text)
    _, pcs, _ = scale_pcs(key)
    head, bars = _split(text)
    for bi in _interior_bars(bars, seed):
        b = bars[bi]
        # a single-note melody token that is IN key -> shift it OUT of key by a semitone
        for li in range(1, len(b)):
            if ":" not in b[li]:
                continue

            def fn(ps, slot, dur, vel):
                if "+" in ps:                              # single notes only (a melody note, not a chord)
                    return None
                m = _midi(ps)
                if m is None or m % 12 not in pcs:
                    return None
                for d in (1, -1):                          # a semitone that lands OUT of key
                    if (m + d) % 12 not in pcs:
                        return _name(m + d)
                return None

            newline, ok, det = _replace_first_tok(b[li], fn)
            if ok:
                nb = list(b); nb[li] = newline
                nbars = list(bars); nbars[bi] = nb
                return _join(head, nbars), dict(bar=bi + 1, kind="out_of_key", voice=_voice(b[li]),
                                                key=key, change=f"{det[0]}->{det[1]}")
    return None, None


def wrong_bass(text, seed=0):
    head, bars = _split(text)
    for bi in _interior_bars(bars, seed):
        b = bars[bi]
        # prefer a voice named like a bass; else the lowest-register voice line
        cand = [li for li in range(1, len(b)) if ":" in b[li] and "bass" in _voice(b[li]).lower()]
        if not cand:
            cand = [li for li in range(1, len(b)) if ":" in b[li]]
        for li in cand:
            def fn(ps, slot, dur, vel):
                root = ps.split("+")[0]
                m = _midi(root)
                if m is None:
                    return None
                new_root = _name(m + 6)                    # tritone off the root — a clearly wrong bass
                rest = ps.split("+")[1:]
                return "+".join([new_root] + rest)

            newline, ok, det = _replace_first_tok(b[li], fn)
            if ok:
                nb = list(b); nb[li] = newline
                nbars = list(bars); nbars[bi] = nb
                return _join(head, nbars), dict(bar=bi + 1, kind="wrong_bass", voice=_voice(b[li]),
                                                change=f"{det[0]}->{det[1]}")
    return None, None


def dissonance(text, seed=0):
    head, bars = _split(text)
    for bi in _interior_bars(bars, seed):
        b = bars[bi]
        for li in range(1, len(b)):
            if ":" not in b[li]:
                continue

            def fn(ps, slot, dur, vel):
                notes = ps.split("+")
                if len(notes) < 2:                         # need a chord to clash against
                    return None
                m = _midi(notes[0])
                if m is None:
                    return None
                clash = _name(m + 1)                       # a minor-2nd cluster on a chord tone
                if clash in notes:
                    return None
                return "+".join(notes + [clash])

            newline, ok, det = _replace_first_tok(b[li], fn)
            if ok:
                nb = list(b); nb[li] = newline
                nbars = list(bars); nbars[bi] = nb
                return _join(head, nbars), dict(bar=bi + 1, kind="dissonance", voice=_voice(b[li]),
                                                change=f"{det[0]}->{det[1]}")
    return None, None


def meter_glitch(text, seed=0):
    head, bars = _split(text)
    for bi in _interior_bars(bars, seed):
        b = bars[bi]
        for li in range(1, len(b)):
            if ":" not in b[li]:
                continue
            # extend the FIRST note's duration by a large amount so the bar overflows its beat grid
            edited = {"done": False, "det": None}

            def _sub(mm):
                if edited["done"]:
                    return mm.group(0)
                ps, slot, dur, vel = mm.group(1), mm.group(2), mm.group(3), mm.group(4) or ""
                newdur = int(dur) + 6                       # +6 slots -> spills past the bar
                edited["done"] = True; edited["det"] = (dur, newdur)
                return f"{ps}@{slot}>{newdur}{vel}"

            newline = _TOK.sub(_sub, b[li])
            if edited["done"]:
                nb = list(b); nb[li] = newline
                nbars = list(bars); nbars[bi] = nb
                return _join(head, nbars), dict(bar=bi + 1, kind="meter_glitch", voice=_voice(b[li]),
                                                change=f"dur {edited['det'][0]}->{edited['det'][1]}")
    return None, None


def _drum_voices(text):
    """Voice names that are percussion ([drums] tag or a drum-like name) — excluded from voice-leading edits."""
    m = re.search(r"VOICES:\s*(.+)", text)
    if not m:
        return set()
    return {v.split("[")[0].strip() for v in m.group(1).split(",")
            if "[drums]" in v or "drum" in v.split("[")[0].lower()}


def _pitched_vlines(b, drums):
    """Indices of voice lines in bar `b` that are pitched (not drums)."""
    return [li for li in range(1, len(b)) if ":" in b[li] and _voice(b[li]) not in drums]


def _line_slots(line):
    """{slot: (full_pitchspec, midi_of_lowest_note)} for a voice line — for slot-aligned voice-leading edits."""
    out = {}
    for mm in _TOK.finditer(line):
        ps, slot = mm.group(1), int(mm.group(2))
        ms = [x for x in (_midi(n) for n in ps.split("+")) if x is not None]
        if ms:
            out[slot] = (ps, min(ms))
    return out


def _set_slot_pitch(line, slot, new_ps):
    """Replace the pitchspec of the token at `slot` (preserving slot/dur/vel), leaving the rest untouched."""
    def _sub(mm):
        if int(mm.group(2)) != slot:
            return mm.group(0)
        return f"{new_ps}@{mm.group(2)}>{mm.group(3)}{mm.group(4) or ''}"
    return _TOK.sub(_sub, line)


def voice_crossing(text, seed=0):
    """Raise a lower voice's note ABOVE a higher voice sounding at the same time — the parts CROSS (a
    voice-leading fault). Targets the bar's lowest single-note token, lifts it above the bar's highest note."""
    head, bars = _split(text)
    drums = _drum_voices(text)
    for bi in _interior_bars(bars, seed):
        b = bars[bi]
        vlines = _pitched_vlines(b, drums)
        if len(vlines) < 2:
            continue
        allnotes = [m for li in vlines for _ps, m in _line_slots(b[li]).values()]
        if not allnotes:
            continue
        hi = max(allnotes)
        for li in vlines:                                    # find a single-note token that is the low voice
            slots = _line_slots(b[li])
            for slot, (ps, m) in slots.items():
                if "+" in ps or m >= hi:
                    continue
                newline = _set_slot_pitch(b[li], slot, _name(hi + 2))   # jump above the top voice
                nb = list(b); nb[li] = newline
                nbars = list(bars); nbars[bi] = nb
                return _join(head, nbars), dict(bar=bi + 1, kind="voice_crossing", voice=_voice(b[li]),
                                                change=f"{ps}->{_name(hi + 2)} (crosses above {_name(hi)})")
    return None, None


def parallel_fifths(text, seed=0):
    """Force two voices into consecutive PARALLEL PERFECT FIFTHS — a classic counterpoint violation. Finds a
    voice with 2 slots of DIFFERENT pitches and another voice sounding at both, and rewrites the second voice
    to a perfect 5th below at both slots, so the pair moves in parallel."""
    head, bars = _split(text)
    drums = _drum_voices(text)
    for bi in _interior_bars(bars, seed):
        b = bars[bi]
        vlines = _pitched_vlines(b, drums)
        for ai in vlines:
            sa = _line_slots(b[ai])
            two = sorted(sa)
            for i in range(len(two) - 1):
                s1, s2 = two[i], two[i + 1]
                if "+" in sa[s1][0] or "+" in sa[s2][0] or sa[s1][1] == sa[s2][1]:
                    continue                                  # need a MOVING mono voice
                for bj in vlines:
                    if bj == ai:
                        continue
                    sb = _line_slots(b[bj])
                    if s1 in sb and s2 in sb:                 # the other voice sounds at both slots
                        line = b[bj]
                        line = _set_slot_pitch(line, s1, _name(sa[s1][1] - 7))
                        line = _set_slot_pitch(line, s2, _name(sa[s2][1] - 7))
                        nb = list(b); nb[bj] = line
                        nbars = list(bars); nbars[bi] = nb
                        return _join(head, nbars), dict(bar=bi + 1, kind="parallel_fifths", voice=_voice(b[bj]),
                                                        change=f"{_voice(b[bj])} moves in parallel 5ths under {_voice(b[ai])}")
    return None, None


KINDS = {"out_of_key": out_of_key, "wrong_bass": wrong_bass, "dissonance": dissonance,
         "meter_glitch": meter_glitch, "voice_crossing": voice_crossing, "parallel_fifths": parallel_fifths}


def inject(text, kind, seed=0):
    """Inject one anomaly of `kind` into a COPY of `text`. Returns (new_text, meta) or (None, None)."""
    return KINDS[kind](text, seed=seed)
