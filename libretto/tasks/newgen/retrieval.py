#!/usr/bin/env python3
"""retrieval.py — MANDATORY idiom retrieval for newgen (KB concepts + real genre exemplars).

Blind from-scratch newgen previously received only abstract dosage numbers ("syncopation ∈ [0.44,0.62]") and
NO examples — the `kb_excerpts` prompt slot was never filled and no exemplar songs were shown. That is the
structural reason newgen trailed the anchored tasks (gaptask/morph see real bars; newgen saw none). An A/B on
latin confirmed injecting these HALVES copy_risk (0.33->0.12, i.e. examples make it *less* copy-prone) and
lifts genre-fit — so retrieval is now a REQUIRED step of newgen setup, not optional.

Two retrieved ingredients per genre:
  1. KB CONCEPTS  — the composing-kb concept entries for the idiom (via the SKILL.md genre->concept map),
     each carrying a real-corpus EXAMPLE + a generative COMPOSE move.
  2. EXEMPLARS    — the k most PROTOTYPICAL real corpus songs of the genre (nearest the genre's fingerprint
     centroid), as short bar excerpts — a style anchor that also teaches the 1-indexed encoding convention.
     Shown as feel reference only; copy stays gated (copy_risk < 0.30), so the model abstracts, not transcribes.
"""
import json, re
from pathlib import Path

import numpy as np

import libretto
from libretto.core import Song  # noqa: F401  (kept for parity / callers)

DATA = libretto.data_root()
KB = DATA / "composing-kb"
GRAMMAR = DATA / "grammar"
KEY = json.loads((DATA / "answer_key" / "grammar_truth.json").read_text())
_FPS = None

# Genre -> KB concept IDs, derived from composing-kb/SKILL.md MAP 1 (umbrella corpus genres unioned from the
# sub-genres listed there). These are the idiom's default building blocks; each entry has EXAMPLE + COMPOSE.
GENRE_CONCEPTS = {
    "latin_reggae_world": ["R-SYNCO", "R-OSTINATO", "H-PEDAL", "R-ROOTPULSE"],
    "core_pop_rock":      ["V-ROLES", "R-SYNCO", "R-STRAIGHT", "M-MOTIF", "F-REPRISE", "H-FOURTHS", "R-OSTINATO"],
    "funk_soul_rnb":      ["R-SYNCO", "R-OSTINATO", "R-ROOTPULSE", "H-PEDAL", "H-DOM7", "H-DIM", "M-SIGH"],
    "jazz":               ["J-IIVI", "J-SWING", "J-COMP", "J-WALK", "J-EXT", "H-DOM7", "M-GAPFILL"],
    "classical":          ["M-STEP", "M-SIGH", "H-PALETTE", "H-DIM", "H-AUG", "V-WIDE", "F-SECTIONS"],
    "electronic_dance":   ["R-ROOTPULSE", "R-STRAIGHT", "R-OSTINATO", "H-PEDAL", "V-WIDE"],
    "film_score":         ["F-SECTIONS", "F-INTRO", "H-PALETTE", "V-WIDE", "H-PEDAL", "M-RANGE"],
    "folk_country":       ["M-STEP", "R-ROOTPULSE", "V-PARALLEL", "V-ROLES", "R-STRAIGHT", "M-SIGH"],
}
_CONCEPT_FILE = {  # which topic file each ID lives in (prefix -> file, J-* in jazz.txt)
    "R": "rhythm_groove.txt", "H": "harmony.txt", "M": "melody.txt",
    "V": "voicing.txt", "F": "form.txt", "J": "jazz.txt",
}


def _fps():
    global _FPS
    if _FPS is None:
        _FPS = {s: np.array(v, float) for s, v in json.loads((DATA / "corpus_fps.json").read_text()).items()}
    return _FPS


def concept_entry(cid):
    """Extract one concept entry (CONCEPT header .. before the next ==== separator) from its topic file."""
    fn = "jazz.txt" if cid.startswith("J-") else _CONCEPT_FILE.get(cid.split("-")[0])
    if not fn or not (KB / fn).exists():
        return None
    lines = (KB / fn).read_text().splitlines()
    start = None
    for i, l in enumerate(lines):
        if l.strip() == f"ID: {cid}":
            j = i
            while j > 0 and not lines[j].startswith("CONCEPT:"):
                j -= 1
            start = j
            break
    if start is None:
        return None
    out = []
    for l in lines[start:]:
        if l.startswith("====") and out:
            break
        out.append(l.rstrip())
    return "\n".join(out).strip()


def concepts_block(genre):
    ids = GENRE_CONCEPTS.get(genre)
    if not ids:
        raise ValueError(f"no KB concept map for genre {genre!r}; add it to GENRE_CONCEPTS (retrieval is mandatory)")
    blocks = [e for e in (concept_entry(c) for c in ids) if e]
    return ids, "\n\n".join(blocks)


def _blocks(text):
    h, b, cur = [], [], None
    for ln in text.splitlines():
        if ln.startswith("@"):
            if cur is not None: b.append(cur)
            cur = [ln]
        elif cur is None: h.append(ln)
        else: cur.append(ln)
    if cur is not None: b.append(cur)
    return h, b


def prototypical_songs(genre, k=2, exclude=None):
    """The k real corpus songs of `genre` NEAREST the genre's fingerprint centroid (most prototypical)."""
    exclude = set(exclude or [])
    fps = _fps()
    ids = [s for s, v in KEY.items() if v.get("genre") == genre and s in fps
           and (GRAMMAR / f"{s}.txt").exists() and s not in exclude]
    if not ids:
        return []
    centroid = np.mean([fps[s] for s in ids], axis=0)
    ids.sort(key=lambda s: float(np.mean(np.abs(fps[s] - centroid))))
    return ids[:k]


def exemplar_excerpt(sid, start=8, n=8):
    """A short, mid-section excerpt (n sounding bars from `start`) of a real song, re-emitted 1-indexed."""
    h, b = _blocks((GRAMMAR / f"{sid}.txt").read_text())
    sounding = [blk for blk in b if len(blk) > 1]
    sl = sounding[start:start + n] or sounding[:n]
    voices = next((l for l in h if l.startswith("VOICES:")), "")
    out = [h[0], voices]
    for i, blk in enumerate(sl, 1):
        bb = list(blk); bb[0] = re.sub(r"^@\d+", f"@{i}", bb[0]); out += bb
    return "\n".join(out)


def build_retrieval(genre, k_exemplars=2, exclude=None):
    """The full retrieval block to inject into a newgen prompt: KB concepts + prototypical exemplars.
    `exclude` drops songs that must not be shown (e.g. a held-out target). Raises if the genre is unmapped."""
    ids, cblock = concepts_block(genre)
    songs = prototypical_songs(genre, k=k_exemplars, exclude=exclude)
    ex_parts = []
    for s in songs:
        title = KEY.get(s, {}).get("title", "")
        ex_parts.append(f"### Exemplar — {s} ({title}) — real {genre}, excerpt (study the FEEL; do NOT copy)\n"
                        f"{exemplar_excerpt(s)}")
    block = (
        f"## STYLE REFERENCE — real {genre} corpus excerpts (most prototypical of the idiom)\n"
        "Learn the groove/feel/voicing from these real songs — then write your OWN material (copy is gated:\n"
        "copy_risk < 0.30, so do not transcribe; abstract the idiom).\n\n"
        + "\n\n".join(ex_parts) +
        "\n\n## KB CONCEPTS FOR THIS IDIOM (composing-kb; apply the COMPOSE moves, dose toward the band MIDDLE)\n"
        + cblock
    )
    return {"genre": genre, "concept_ids": ids, "exemplar_ids": songs, "text": block}
