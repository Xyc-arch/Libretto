#!/usr/bin/env python3
"""verify — check a piece against all 6 anomaly conditions. Used to (a) VERIFY that a generated clean chorale
is truly anomaly-free before it becomes a clean-control case, and (b) serve as a transparent rule-detector
baseline. is_clean(text) -> (clean_bool, [flags]); each flag names the bar + kind it tripped."""
import re

import pretty_midi as pm

from libretto.tasks.anomaly.inject import _split, _midi, _drum_voices, _voice, _TOK
from libretto.tasks.education.measure import scale_pcs

_ORDER = ["bass", "tenor", "alto", "soprano"]     # expected ascending register order, if named


def _bar_notes(bar, drums):
    """{voice_name: [midis]} for a bar (pitched voices only)."""
    out = {}
    for ln in bar[1:]:
        if ":" not in ln or _voice(ln) in drums:
            continue
        ms = []
        for mm in _TOK.finditer(ln):
            ms += [x for x in (_midi(n) for n in mm.group(1).split("+")) if x is not None]
        if ms:
            out[_voice(ln)] = ms
    return out


def _triad_root(pcs):
    """If the pitch-class set forms a (maj/min) triad, return its root pc; else None."""
    s = set(pcs)
    for r in s:
        if {(r + 4) % 12, (r + 7) % 12} <= s or {(r + 3) % 12, (r + 7) % 12} <= s:
            return r
    return None


def _parallel_perfect(a, b):
    for i in range(len(a)):
        for j in range(i + 1, len(a)):
            i0, i1 = abs(a[i] - a[j]) % 12, abs(b[i] - b[j]) % 12
            if i0 in (0, 7) and i1 in (0, 7) and i0 == i1:
                d1, d2 = b[i] - a[i], b[j] - a[j]
                if d1 and d2 and (d1 > 0) == (d2 > 0):
                    return True
    return False


def is_clean(text):
    """Return (clean, flags). Checks out_of_key, dissonance, wrong_bass, meter_glitch, voice_crossing,
    parallel_fifths on a bar-per-chord homophonic piece (as produced by clean_source)."""
    _, pcs, _ = scale_pcs((re.search(r"KEY:\s*([^|]+)", text) or [None, "C major"])[1].strip())
    mm = re.search(r"METER:\s*(\d+)/(\d+)", text)
    bar_slots = 16 if not mm else int(mm.group(1)) * 16 // int(mm.group(2))
    drums = _drum_voices(text)
    _, bars = _split(text)
    flags = []
    prev_ordered = None
    for bi, b in enumerate(bars, 1):
        bn = _bar_notes(b, drums)
        if not bn:
            continue
        allm = [m for ms in bn.values() for m in ms]
        allpc = {m % 12 for m in allm}
        # out_of_key
        if any(m % 12 not in pcs for m in allm):
            flags.append((bi, "out_of_key"))
        # dissonance: simultaneous semitone cluster
        s = sorted(allm)
        if any(s[i + 1] - s[i] == 1 for i in range(len(s) - 1)):
            flags.append((bi, "dissonance"))
        # wrong_bass: lowest note is not the triad root
        root = _triad_root(allpc)
        if root is not None and min(allm) % 12 != root:
            flags.append((bi, "wrong_bass"))
        # meter_glitch: a note runs past the bar's slot budget
        overflow = False
        for ln in b[1:]:
            for tk in _TOK.finditer(ln):
                if int(tk.group(2)) + int(tk.group(3)) - 1 > bar_slots:
                    overflow = True
        if overflow:
            flags.append((bi, "meter_glitch"))
        # voice_crossing: if voices are the named SATB set, they must ascend bass<tenor<alto<soprano
        named = {k.lower(): v[0] for k, v in bn.items() if k.lower() in _ORDER and len(v) == 1}
        if len(named) == 4:
            seq = [named[o] for o in _ORDER]
            if seq != sorted(seq):
                flags.append((bi, "voice_crossing"))
            # parallel_fifths vs previous bar
            if prev_ordered and _parallel_perfect(prev_ordered, seq):
                flags.append((bi, "parallel_fifths"))
            prev_ordered = seq
    return (len(flags) == 0, flags)


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        clean, flags = is_clean(open(p).read())
        print(f"{p}: {'CLEAN' if clean else 'flags=' + str(flags)}")
