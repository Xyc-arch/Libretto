#!/usr/bin/env python3
"""retrieval.py — kb_theory browse + classical-exemplar retrieval for the education task.

The education task is RETRIEVAL-FIRST: given a learner's required challenge (a rhythm, key, scale, chord,
progression, melodic device, texture, articulation, or form), it browses kb_theory for the matching concept
entries (each carries WHAT + CHALLENGE + a renderable single-voice-piano GRAMMAR example), then optionally
pulls a prototypical CLASSICAL corpus excerpt for phrasing/contour flavour. Those become the generation
context. The kb GRAMMAR examples are shown as *reference for the device* — the generated piece must invent
its own material (novelty is gated in measure.py).
"""
import re
from pathlib import Path

import libretto
from libretto.tasks.newgen import retrieval as _newgen_R   # reuse prototypical-song + excerpt helpers

KB = libretto.data_root() / "kb_theory"
_ENTRIES = None

_ENTRY_RE = re.compile(
    r"CONCEPT:\s*(.+?)\nID:\s*(\S+)\nCATEGORY:\s*(\S+)\nLEVEL:\s*(\S+)\n"
    r"WHAT:\s*(.*?)\nCHALLENGE:\s*(.*?)\nGRAMMAR-BEGIN\n(.*?)\nGRAMMAR-END", re.S)


def _load():
    out = {}
    for f in sorted(KB.glob("*.txt")):
        for m in _ENTRY_RE.finditer(f.read_text()):
            out[m.group(2)] = dict(id=m.group(2), concept=m.group(1).strip(), category=m.group(3),
                                   level=m.group(4), what=m.group(5).strip(), challenge=m.group(6).strip(),
                                   grammar=m.group(7).strip(), file=f.name)
    return out


def entries():
    global _ENTRIES
    if _ENTRIES is None:
        _ENTRIES = _load()
    return _ENTRIES


def concept(cid):
    e = entries().get(cid)
    if e is None:
        raise KeyError(f"no kb_theory concept {cid!r} (browse with by_category/search)")
    return e


def by_category(category):
    return {k: v for k, v in entries().items() if v["category"] == category}


def by_level(level):
    return {k: v for k, v in entries().items() if v["level"] == level}


def search(term):
    t = term.lower()
    return {k: v for k, v in entries().items()
            if t in v["concept"].lower() or t in v["what"].lower() or t in k.lower()
            or t in v["category"].lower()}


def classical_exemplar(k=1):
    """Short excerpt(s) of the most prototypical CLASSICAL corpus song(s) — style/contour reference only."""
    out = []
    for s in _newgen_R.prototypical_songs("classical", k=k):
        out.append((s, _newgen_R.exemplar_excerpt(s)))
    return out


def build_context(concept_ids, *, with_exemplar=True):
    """Assemble the retrieved kb_theory concepts (+ optional classical exemplar) into a prompt context.
    Returns the text block plus `shown_grammars` (used by measure.py to gate copy against what was shown)."""
    cons = [concept(c) for c in concept_ids]
    lines = ["## REQUIRED-CHALLENGE CONCEPTS (from kb_theory — study WHAT/CHALLENGE; the GRAMMAR shows the",
             "## device only, do NOT copy it — invent your own notes):"]
    for e in cons:
        lines += [f"\n### {e['id']} — {e['concept']}  [{e['category']}, {e['level']}]",
                  f"WHAT: {e['what']}", f"CHALLENGE: {e['challenge']}",
                  "EXAMPLE (reference for the device — write DIFFERENT notes):", e["grammar"]]
    shown = [e["grammar"] for e in cons]
    ex_ids = []
    if with_exemplar:
        ex = classical_exemplar(1)
        if ex:
            sid, exg = ex[0]; ex_ids = [sid]; shown.append(exg)
            lines.append(f"\n## CLASSICAL STYLE REFERENCE — {sid} (phrasing/contour inspiration ONLY; your "
                         f"output is SINGLE-VOICE piano — do not copy these notes):\n{exg}")
    return {"concept_ids": concept_ids, "exemplar_ids": ex_ids, "shown_grammars": shown,
            "text": "\n".join(lines)}
