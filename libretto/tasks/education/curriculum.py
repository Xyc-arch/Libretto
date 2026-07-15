#!/usr/bin/env python3
"""curriculum.py — difficulty auto-scaler + requirement helpers for the education task.

`autoscale(level, dimensions, n)` picks a concept set from kb_theory appropriate to a difficulty LEVEL,
spread across the requested challenge DIMENSIONS (rhythm / scale / chord / progression / melody / texture /
form / articulation). Deterministic (no RNG): rotates through dimensions and takes from the level pool.

Also resolves user-facing requirements: qualitative tempo words -> BPM, and a rhythm "feel" (fast/slow) ->
the expected note-density / note-value profile the measure checks.
"""
# Concept pools per level (IDs from kb_theory). Higher levels add harder devices.
LEVEL_POOLS = {
    "beginner": {
        "rhythm": ["TR-QUARTER-NOTE", "TR-HALF-NOTE", "TR-WHOLE-NOTE", "TR-PAT-FOUR-QUARTERS",
                   "TR-EIGHTH-NOTE", "TR-PAT-HALF-HALF", "TR-REST"],
        "meter": ["TR-METER-44", "TR-METER-34"],
        "scale": ["TS-MAJOR-SCALE", "TS-NATURAL-MINOR", "TS-MAJOR-PENTATONIC"],
        "key": ["TS-KEY-C-MAJOR", "TS-KEY-G-MAJOR", "TS-KEY-A-MINOR"],
        "chord": ["TC-MAJOR-TRIAD", "TC-MINOR-TRIAD", "TC-POWER-CHORD"],
        "progression": ["TP-I-IV-V", "TP-I-V-VI-IV"],
        "melody": ["TM-STEPWISE", "TM-MOTIF", "TM-REPETITION", "TM-PHRASE"],
        "texture": ["TX-BLOCK-CHORDS", "TX-MONOPHONIC", "TX-BROKEN-CHORDS"],
        "form": ["TF-BINARY", "TF-STROPHIC"],
    },
    "intermediate": {
        "rhythm": ["TR-DOTTED-NOTE", "TR-PAT-DOTTED-LONG-SHORT", "TR-SYNCOPATION", "TR-SIXTEENTH-NOTE",
                   "TR-PAT-SIXTEENTH-RUN", "TR-TIE", "TR-PAT-SYNCOPATED-RHYTHM", "TR-PAT-FOUR-EIGHTHS"],
        "meter": ["TR-METER-68", "TR-METER-24", "TR-METER-34"],
        "scale": ["TS-HARMONIC-MINOR", "TS-DORIAN", "TS-MIXOLYDIAN", "TS-MINOR-PENTATONIC",
                  "TS-BLUES-SCALE", "TS-MELODIC-MINOR"],
        "key": ["TS-KEY-F-MAJOR", "TS-KEY-E-MINOR", "TS-KEY-D-MINOR"],
        "chord": ["TC-MAJ7", "TC-MIN7", "TC-DOM7", "TC-SUS4", "TC-SUS2", "TC-SIX"],
        "progression": ["TP-II-V-I", "TP-VI-IV-I-V", "TP-i-VI-III-VII", "TP-I-bVII-IV-I", "TP-i-iv-V-i"],
        "melody": ["TM-LEAP", "TM-SEQUENCE", "TM-CONTOUR", "TM-CALL-RESPONSE", "TM-PASSING-TONE",
                   "TM-NEIGHBOR-TONE", "TM-CLIMAX", "TM-VARIATION"],
        "texture": ["TX-ARPEGGIO", "TX-ALBERTI-BASS", "TX-HOMOPHONIC", "TX-OCTAVES"],
        "form": ["TF-TERNARY", "TF-VERSE-CHORUS", "TF-12BAR-BLUES", "TF-THEME-VARIATIONS"],
    },
    "advanced": {
        "rhythm": ["TR-TRIPLET", "TR-PAT-TRIPLET-RHYTHM", "TR-METER-128", "TR-PAT-DOTTED-SHORT-LONG",
                   "TR-SYNCOPATION", "TR-PAT-SIXTEENTH-RUN"],
        "meter": ["TR-METER-128", "TR-METER-68"],
        "scale": ["TS-LYDIAN", "TS-PHRYGIAN", "TS-LOCRIAN", "TS-WHOLE-TONE", "TS-CHROMATIC-SCALE",
                  "TS-MELODIC-MINOR"],
        "key": ["TS-KEY-D-MINOR", "TS-KEY-E-MINOR", "TS-KEY-F-MAJOR"],
        "chord": ["TC-HALFDIM7", "TC-DIM7", "TC-AUG-TRIAD", "TC-NINE", "TC-ADD9", "TC-MAJ7"],
        "progression": ["TP-i-VII-VI-VII", "TP-i-VI-III-VII", "TP-II-V-I"],
        "melody": ["TM-APPOGGIATURA", "TM-SUSPENSION", "TM-RESOLUTION", "TM-SEQUENCE", "TM-CONTOUR"],
        "texture": ["TX-POLYPHONIC", "TX-ARPEGGIO", "TX-OCTAVES"],
        "articulation": ["TE-TRILL", "TE-MORDENT", "TE-TURN", "TE-GRACE"],
        "form": ["TF-RONDO", "TF-THROUGH-COMPOSED", "TF-THEME-VARIATIONS"],
    },
}
DEFAULT_DIMS = {"beginner": ["rhythm", "scale", "melody"],
                "intermediate": ["rhythm", "scale", "chord", "melody"],
                "advanced": ["rhythm", "scale", "chord", "melody", "articulation"]}

# Richer per-level DEFAULTS — pitched a notch higher so auto-generated practice is interesting, not trivial:
# longer pieces, livelier tempo, a baseline of syncopation, a real melodic range, more concepts in play.
# (Range is in semitones — moderate, deliberately LESS strict than full classical melodic writing.)
LEVEL_DEFAULTS = {
    "beginner":     dict(bars=16, tempo="moderate", syncopation="light",    range_min=9,  n_concepts=3, melody_interest=True),
    "intermediate": dict(bars=20, tempo="allegro",  syncopation="moderate", range_min=14, n_concepts=4, melody_interest=True),
    "advanced":     dict(bars=24, tempo="vivace",   syncopation="moderate", range_min=17, n_concepts=5, melody_interest=True),
}


def level_defaults(level):
    return LEVEL_DEFAULTS.get(level, LEVEL_DEFAULTS["beginner"])

TEMPO_WORDS = {"largo": 50, "very slow": 50, "adagio": 66, "slow": 66, "andante": 84, "walking": 84,
               "moderato": 100, "moderate": 100, "allegro": 138, "fast": 138, "vivace": 156, "lively": 156,
               "presto": 176, "very fast": 176}

# Tempo + meter VARIETY: a drill batch should cover the MAJOR speed range (not one fixed tempo) and varied
# time signatures (not only 4/4). Cycled by the spec's `variant`, so successive drills (variant 0,1,2,…) walk
# the ladder — a batch of N drills spans slow→fast and several meters. Each level's window stays
# level-appropriate (beginners never land on presto/12-8; advanced never sits at largo/2-4).
TEMPO_LADDER = {
    "beginner":     ["adagio", "andante", "moderato", "allegro"],
    "intermediate": ["andante", "moderato", "allegro", "vivace"],
    "advanced":     ["moderato", "allegro", "vivace", "presto"],
}
METER_LADDER = {
    "beginner":     ["4/4", "3/4", "2/4"],
    "intermediate": ["4/4", "3/4", "6/8", "2/4"],
    "advanced":     ["4/4", "3/4", "6/8", "12/8"],
}


def tempo_for_variant(level, variant=0):
    """A level-appropriate tempo word, cycled by variant so a batch covers the major speed range."""
    lad = TEMPO_LADDER.get(level, TEMPO_LADDER["beginner"])
    return lad[int(variant) % len(lad)]


def meter_for_variant(level, variant=0):
    """A level-appropriate time signature, cycled by variant so a batch is not all 4/4."""
    lad = METER_LADDER.get(level, METER_LADDER["beginner"])
    return lad[int(variant) % len(lad)]


def autoscale(level, dimensions=None, n=3, offset=0):
    """Deterministically pick `n` kb_theory concept IDs for a level, rotating across `dimensions`."""
    level = level if level in LEVEL_POOLS else "beginner"
    dims = [d for d in (dimensions or DEFAULT_DIMS[level]) if d in LEVEL_POOLS[level]]
    if not dims:
        dims = DEFAULT_DIMS[level]
    picked, i = [], 0
    while len(picked) < n and i < n * len(dims) + len(dims):
        d = dims[i % len(dims)]
        pool = LEVEL_POOLS[level][d]
        cand = pool[(offset + i // len(dims)) % len(pool)]
        if cand not in picked:
            picked.append(cand)
        i += 1
    return picked


def tempo_bpm(tempo):
    """Resolve a tempo spec (a word like 'fast', an int, or [lo,hi]) to a target BPM + an accept range."""
    if isinstance(tempo, (list, tuple)) and len(tempo) == 2:
        lo, hi = tempo; return (lo + hi) // 2, (lo, hi)
    if isinstance(tempo, (int, float)):
        return int(tempo), (int(tempo) - 12, int(tempo) + 12)
    bpm = TEMPO_WORDS.get(str(tempo).lower().strip(), 100)
    return bpm, (bpm - 18, bpm + 18)


# syncopation AMOUNT -> target off-beat-onset ratio band (educator can ask for small vs large syncopation).
SYNCOPATION_BANDS = {
    "none": (0.0, 0.08), "straight": (0.0, 0.08),
    "light": (0.10, 0.32), "small": (0.10, 0.32), "a little": (0.10, 0.32),
    "moderate": (0.30, 0.55), "medium": (0.30, 0.55), "some": (0.30, 0.55),
    "heavy": (0.50, 0.95), "large": (0.50, 0.95), "a lot": (0.50, 0.95), "strong": (0.50, 0.95),
}


def syncopation_band(amount):
    return SYNCOPATION_BANDS.get(str(amount).lower().strip())


def rhythm_feel_target(feel):
    """A rhythm 'feel' -> expected profile the measure checks. fast = short predominant values + dense onsets."""
    f = str(feel).lower().strip()
    if f in ("fast", "driving", "busy"):
        return {"feel": "fast", "max_median_dur": 0.5, "min_onsets_per_bar": 4.0}
    if f in ("slow", "calm", "sparse"):
        return {"feel": "slow", "min_median_dur": 1.0, "max_onsets_per_bar": 4.0}
    return {"feel": "moderate", "min_median_dur": 0.4, "max_median_dur": 1.5}
