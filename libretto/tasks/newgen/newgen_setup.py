#!/usr/bin/env python3
"""newgen_setup.py — prep for REAL from-scratch generation (no source song, no seam).

Two modes:
  genre <name>  — compose a full piece IN a target genre. Targets = the genre-conditioned bands on the 8
                  split axes (aim p50) + the global idiomatic band on the rest. Retrieval is MANDATORY in
                  this mode: the prompt always carries the genre's KB concepts (EXAMPLE + COMPOSE) and the
                  most prototypical real corpus exemplars (see retrieval.py). Blind dosage numbers alone do
                  not teach an idiom — examples do (and they lower copy_risk, not raise it).
  brief "<txt>" — compose to a user STYLE + EMOTION brief; no genre band (emotion isn't objectively
                  measurable). No genre-specific retrieval (there's no genre to retrieve for).

The verdict criteria are ADAPTIVE / genre-calibrated (see calibrate.py): C1 budget and the band-fit floor
are set from what real corpus songs of the genre achieve. Writes a complete generation prompt + case.json.

Usage:
  python3 -m libretto.tasks.newgen.newgen_setup genre jazz [outdir]
  python3 -m libretto.tasks.newgen.newgen_setup brief "wistful, tender — a slow lyrical ballad" [outdir]
"""
import json, sys
from pathlib import Path

import libretto
from libretto.generation.interface import load_prompt, PROMPTS
from . import calibrate as cal
from . import retrieval as R

DATA = libretto.data_root()
CANON = json.loads((DATA / "corpus_distribution_314.json").read_text())
GC = CANON["genre_conditioned"]; SPLIT = list(GC.keys())
LEN_LO, LEN_HI = 64, 179


def gband(ax, genre):
    b = GC[ax][genre]
    return round(b["p25"], 3), round(b["p50"], 3), round(b["p75"], 3)


def _bands_text(genre):
    return "\n".join(f"    - {ax}: stay in [{gband(ax,genre)[0]}, {gband(ax,genre)[2]}], aim ~{gband(ax,genre)[1]}"
                     for ax in SPLIT)


def build_genre_prompt(genre, length=96, exclude=None):
    """Full from-scratch genre prompt with MANDATORY retrieval baked in. Raises if the genre is unmapped."""
    template = load_prompt("newgen"); shared = (PROMPTS / "_shared.md").read_text(encoding="utf-8")
    retr = R.build_retrieval(genre, exclude=exclude)          # mandatory — raises if no concept map
    budget = cal.c1_budget(genre); fit_thr = cal.fit_threshold(genre)
    prompt = f"""{template}

---
## GRAMMAR FORMAT (shared)
{shared}

---
{retr['text']}

---
## YOUR CASE
- TARGET GENRE: {genre}
- Compose a full ~{length}-bar piece IN {genre} with a clear, REPEATED groove and sectional form
  (reuse whole 2-/4-bar units — a fresh bar every bar reads as degenerate).
- length_bars: aim ~{length} (must be within [{LEN_LO},{LEN_HI}])
- Genre mid-band dosage targets (the 8 split axes — aim the MIDDLE, not the ceiling):
{_bands_text(genre)}
- ALL OTHER axes: stay inside the global idiomatic band (no extremes).

## OUTPUT CONTRACT
Return ONLY the full grammar block (no prose/fences): line 1 the KEY/METER/TEMPO/GRID/BARS header, line 2
the VOICES line, then all numbered bar blocks. Make it read as {genre}.
"""
    case = dict(mode="genre", genre=genre, length_target=[LEN_LO + 16, 120], name=f"newgen_{genre}",
                c1_budget=budget, fit_threshold=fit_thr,
                concept_ids=retr["concept_ids"], exemplar_ids=retr["exemplar_ids"])
    return prompt, case


def build_brief_prompt(brief_txt, length=96):
    template = load_prompt("newgen"); shared = (PROMPTS / "_shared.md").read_text(encoding="utf-8")
    prompt = f"""{template}

---
## GRAMMAR FORMAT (shared)
{shared}

---
## YOUR CASE (style/emotion brief — NO target genre)
- BRIEF: {brief_txt}
- length_bars: aim ~{length} (must be within [{LEN_LO},{LEN_HI}])
- Gated only on: full length, non-degeneracy (mid-band dosage, no extreme axes), genuine novelty
  (copy_risk < 0.30 vs corpus). Emotion/style match is the instruction, not a metric.
- Write a complete multi-voice arrangement with clear, REPEATED sections; dose traits toward the middle.

## OUTPUT CONTRACT
Return ONLY the full grammar block (no prose/fences): the KEY/METER/TEMPO/GRID/BARS header, the VOICES line,
then all numbered bar blocks.
"""
    case = dict(mode="brief", genre=None, brief=brief_txt, length_target=[LEN_LO + 16, 120], name="newgen_brief")
    return prompt, case


def main(mode, arg, outdir="compositions/newgen"):
    out = Path(outdir); out.mkdir(parents=True, exist_ok=True)
    if mode == "genre":
        assert any(arg in GC[ax] for ax in SPLIT), f"unknown genre {arg}"
        prompt, case = build_genre_prompt(arg)
        (out / f"genprompt_newgen_{arg}.txt").write_text(prompt, encoding="utf-8")
        (out / f"newgen_{arg}_case.json").write_text(json.dumps(case, indent=2))
        print(f"=== NEWGEN SETUP (from scratch, adaptive + mandatory retrieval) — genre={arg} ===")
        print(f"  C1 budget={case['c1_budget']}  fit_threshold={case['fit_threshold']} (genre-calibrated)")
        print(f"  retrieved concepts: {case['concept_ids']}")
        print(f"  prototypical exemplars: {case['exemplar_ids']}")
        print(f"  wrote {out}/genprompt_newgen_{arg}.txt + case.json")
    else:
        prompt, case = build_brief_prompt(arg)
        (out / "genprompt_newgen_brief.txt").write_text(prompt, encoding="utf-8")
        (out / "newgen_brief_case.json").write_text(json.dumps(case, indent=2))
        print(f"=== NEWGEN SETUP (from scratch) — STYLE/EMOTION brief ===")
        print(f"  brief: {arg!r}  (no genre band; no genre retrieval)")
        print(f"  wrote {out}/genprompt_newgen_brief.txt + case.json")


if __name__ == "__main__":
    a = sys.argv
    main(a[1], a[2], a[3] if len(a) > 3 else "compositions/newgen")
