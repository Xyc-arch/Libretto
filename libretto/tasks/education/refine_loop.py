#!/usr/bin/env python3
"""refine_loop.py — regenerate an education practice piece until its required challenge + requirements are met.

generate -> measure -> if a challenge/requirement/key/novelty check failed, turn the failures into corrective
feedback and regenerate (<= max_iter rounds), pick the best round. Leakage-free by construction (the gate is
all structural + vs the frozen corpus / shown material).
"""
from pathlib import Path

from . import setup as S
from . import measure as M


def feedback(report):
    """Turn a measure report's failures into musician-readable corrections for the next round."""
    lines = []
    if not report["in_key"]:
        lines.append(f"STAY IN KEY: {report['out_of_scale_frac']*100:.0f}% of notes were outside "
                     f"{report['key']}; keep notes in that scale (only the listed device may add chromatics).")
    for c in report["challenge_checks"]:
        if c["pass"] is False:
            lines.append(f"CHALLENGE not met — {c['check']}: exercise this device more clearly/often.")
    for c in report["requirement_checks"]:
        if c["pass"] is False:
            lines.append(f"REQUIREMENT not met — {c['check']}: fix this exactly.")
    if report["copy_vs_shown"] >= report["copy_vs_shown_thr"]:
        lines.append(f"NOVELTY: you reproduced the shown example (overlap {report['copy_vs_shown']:.2f}); "
                     f"invent DIFFERENT notes for the same device.")
    if report["copy_vs_corpus"] >= report["copy_vs_corpus_thr"]:
        lines.append(f"NOVELTY: too close to an existing song (overlap {report['copy_vs_corpus']:.2f}); "
                     f"make the line more distinctive.")
    return lines


def _score(report):
    """Lower = better. Count failed gate components (challenge/requirement counted per-check)."""
    fails = 0
    fails += 0 if report["single_channel"] else 1
    fails += 0 if report["in_key"] else 1
    fails += sum(1 for c in report["challenge_checks"] if c["pass"] is False)
    fails += sum(1 for c in report["requirement_checks"] if c["pass"] is False)
    fails += 0 if report["novel"] else 1
    return fails


class RefinementLoop:
    """Drive generate -> measure -> corrective regenerate for an education ChallengeSpec. Plug any Generator
    (`.generate(prompt, context) -> grammar text`). Returns (best_report, [all rounds])."""

    def __init__(self, generator, max_iter=3):
        self.generator = generator
        self.max_iter = max_iter

    def run(self, spec, workdir=".", label="practice"):
        workdir = Path(workdir); workdir.mkdir(parents=True, exist_ok=True)
        rounds, best, corrections = [], None, None
        for r in range(1, self.max_iter + 1):
            prompt, case = S.build_prompt(spec, corrections=corrections)
            grammar = self.generator.generate(prompt, {})
            p = workdir / f"{label}_r{r}.txt"; p.write_text(grammar, encoding="utf-8")
            _strip_prose(p)
            rep = M.measure(p, case); rep["round"] = r; rep["path"] = str(p)
            rep["score"] = _score(rep); rounds.append(rep)
            if best is None or rep["score"] < best["score"]:
                best = rep
            if rep["verdict"]:
                break
            corrections = feedback(rep)
        return best, rounds


def _strip_prose(p):
    ls = p.read_text().splitlines()
    ki = next((i for i, l in enumerate(ls) if l.strip().startswith("KEY:")), 0)
    if ki > 0:
        p.write_text("\n".join(ls[ki:]) + "\n")
