#!/usr/bin/env python3
"""clean_source — generate GENUINELY theory-clean 4-voice chorales for the anomaly clean-control.

Real songs cannot be a "clean" control: they idiomatically contain the very features we inject (chromatic
notes, inversion basses, clusters, sustains over barlines). So we synthesise clean-by-construction diatonic
chorales — bass = chord root, only diatonic triad tones, voices strictly ordered (no crossing), whole-note
harmonic rhythm (no meter overflow) — and VERIFY each against all 6 anomaly checks, keeping only pieces that
pass (rejection sampling on seed). A false positive on these is a genuine model call, not a corpus artifact.

    python -m libretto.tasks.anomaly.clean_source --n 4 --bars 12 --seed 1   # prints/samples clean pieces
"""
import random

import pretty_midi as pm

MAJ = [0, 2, 4, 5, 7, 9, 11]                                     # major scale degrees
TONICS = {"C": 60, "G": 67, "F": 65, "D": 62, "Bb": 58, "A": 69, "Eb": 63}
# diatonic triads by scale degree (root-position pc offsets within the scale): triad = degrees d, d+2, d+4
DEGREE_TRIAD = {i: (i, (i + 2) % 7, (i + 4) % 7) for i in range(7)}
# a simple functional progression pool (scale-degree roots, 0=I): all diatonic, common practice
PROGRESSIONS = [
    [0, 3, 4, 0], [0, 5, 3, 4], [0, 4, 5, 3], [0, 1, 4, 0], [0, 3, 1, 4],
    [0, 5, 1, 4], [5, 3, 0, 4], [0, 2, 3, 4],
]


def _tri_pcs(tonic_pc, deg):
    """The 3 pitch classes of the diatonic triad on scale degree `deg`."""
    root_deg, third_deg, fifth_deg = DEGREE_TRIAD[deg]
    return [(tonic_pc + MAJ[d]) % 12 for d in (root_deg, third_deg, fifth_deg)]


def _nearest(pc, ref, lo, hi):
    """A midi note of pitch-class `pc` in [lo,hi] closest to `ref`."""
    cands = [m for m in range(lo, hi + 1) if m % 12 == pc]
    return min(cands, key=lambda m: abs(m - ref)) if cands else None


def _voicings(pcs):
    """All complete-triad SATB voicings for triad `pcs` (root,3rd,5th): bass=root; the 3 upper voices carry
    3rd, 5th and one doubled tone, placed in ascending tenor/alto/soprano registers. Returns list of 4-midi
    tuples (bass, tenor, alto, soprano), strictly ascending."""
    import itertools
    root, third, fifth = pcs
    out = []
    bass_opts = [m for m in range(40, 53) if m % 12 == root]
    upper_pcs = [third, fifth, root, fifth, third]              # must include 3rd & 5th; extra = a doubling
    for bass in bass_opts:
        # choose the 3 upper pitch classes: {3rd, 5th} + one of {root,3rd,5th}
        for extra in (root, third, fifth):
            triple = [third, fifth, extra]
            regs = [(bass + 1, 64), (55, 72), (60, 81)]         # tenor, alto, soprano
            cand_lists = []
            for pc, (lo, hi) in zip(sorted(triple), regs):      # rough low->high assignment by pc is not ideal;
                cand_lists.append([m for m in range(lo, hi + 1) if m % 12 == pc])
            for t, a, s in itertools.product(*cand_lists):
                v = (bass, t, a, s)
                if v == tuple(sorted(v)) and len(set(v)) >= 3:
                    out.append(v)
    return out


def _voice_progression(prog, tonic_pc, rng):
    """Greedy voice-leading: pick, for each chord, the complete-triad voicing nearest the previous one that
    creates NO parallel perfect 5th/8ve. Returns the list of 4-midi bars, or None if it gets stuck."""
    voiced = []
    prev = None
    for deg in prog:
        cands = _voicings(_tri_pcs(tonic_pc, deg))
        rng.shuffle(cands)
        if prev is not None:
            cands = [v for v in cands if not _parallel_perfect(prev, v)]
            cands.sort(key=lambda v: sum(abs(v[i] - prev[i]) for i in range(4)))
        if not cands:
            return None
        v = cands[0]
        voiced.append(list(v)); prev = v
    return voiced


def _parallel_perfect(a, b):
    """True if voice-pair moves in parallel perfect 5th/octave between chords a->b (both same interval class,
    both voices move nonzero in the same direction)."""
    for i in range(len(a)):
        for j in range(i + 1, len(a)):
            i0, i1 = abs(a[i] - a[j]) % 12, abs(b[i] - b[j]) % 12
            if i0 in (0, 7) and i1 in (0, 7) and i0 == i1:
                d1, d2 = b[i] - a[i], b[j] - a[j]
                if d1 != 0 and d2 != 0 and (d1 > 0) == (d2 > 0):
                    return True
    return False


def _to_grammar(key, voiced, tonic_pc):
    head = [f"KEY: {key} major | METER: 4/4 | TEMPO: 88 | GRID: 16th | BARS: {len(voiced)}",
            "VOICES: Bass[prog=0], Tenor[prog=0], Alto[prog=0], Soprano[prog=0]"]
    names = ["Bass", "Tenor", "Alto", "Soprano"]
    lines = []
    for bi, v in enumerate(voiced, 1):
        lines.append(f"@{bi} [-]")
        for n, m in zip(names, v):
            lines.append(f"  {n}: {pm.note_number_to_name(m)}@1>16")
    return "\n".join(head + lines) + "\n"


def clean_piece(key="C", bars=12, seed=0):
    """A verified-clean diatonic chorale. Rejection-samples until a piece passes all 6 anomaly checks."""
    from libretto.tasks.anomaly.verify import is_clean
    tonic_pc = TONICS[key] % 12
    for attempt in range(200):
        rng = random.Random(f"{seed}-{attempt}")
        prog = []
        while len(prog) < bars:
            prog += rng.choice(PROGRESSIONS)
        prog = prog[:bars]
        voiced = _voice_progression(prog, tonic_pc, rng)
        if voiced is None or len(voiced) != bars:
            continue
        text = _to_grammar(key, voiced, tonic_pc)
        if is_clean(text)[0]:
            return text
    return None


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n", type=int, default=4)
    ap.add_argument("--bars", type=int, default=12)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    keys = list(TONICS)
    ok = 0
    for i in range(a.n):
        t = clean_piece(keys[i % len(keys)], a.bars, a.seed + i)
        print(f"[{i}] key {keys[i % len(keys)]}: {'clean piece OK' if t else 'FAILED to sample clean'}")
        ok += bool(t)
    print(f"{ok}/{a.n} clean pieces generated")


if __name__ == "__main__":
    main()
