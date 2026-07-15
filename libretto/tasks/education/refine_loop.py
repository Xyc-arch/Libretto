#!/usr/bin/env python3
"""refine_loop.py — regenerate an education practice piece until its required challenge + requirements are met.

generate -> measure -> if a challenge/requirement/key/novelty check failed, turn the failures into corrective
feedback and regenerate (<= max_iter rounds), pick the best round. Leakage-free by construction (the gate is
all structural + vs the frozen corpus / shown material).
"""
import re
from pathlib import Path

from . import setup as S
from . import measure as M


def _req_fix(check):
    """A CONCRETE, actionable correction for a failed requirement check (not just a restatement)."""
    cl = check.lower()
    if "syncopation" in cl:
        m = re.search(r"ratio ([\d.]+) in \[([\d.]+),([\d.]+)\]", check)
        cur, lo, hi = (float(m.group(1)), float(m.group(2)), float(m.group(3))) if m else (0.0, 0.30, 0.55)
        if cur < lo:
            pct = int(round((lo + hi) / 2 * 100))
            return (f"SYNCOPATION TOO LOW (off-beat ratio {cur:.2f}, MUST be {lo:.2f}-{hi:.2f}): put about "
                    f"{pct}% of note ONSETS OFF the beat. In a 16th 4/4 bar the DOWNBEATS are slots 1,5,9,13 — "
                    f"put FEWER onsets there and MORE on the off-beats 3,7,11,15 (the '&' of each beat) and the "
                    f"16th-offbeats 2,4,6,8,10,12,14,16. Use syncopated cells like `>2 >4 >2` (eighth, then a "
                    f"quarter that ATTACKS on the '&' at slot 3 or 7 or 11 and TIES across the next beat, then an "
                    f"eighth) and dotted `>3 >1`; tie notes across the beat. Do NOT land nearly every note on "
                    f"1/5/9/13 — that reads as zero syncopation.")
        return (f"SYNCOPATION TOO HIGH (off-beat ratio {cur:.2f}, MUST be {lo:.2f}-{hi:.2f}): anchor MORE onsets "
                f"ON the beat (slots 1,5,9,13) and fewer on the off-beats.")
    if "grand-staff" in cl or "freq-balance" in cl or "busiest octave" in cl:
        return ("REGISTER BALANCE not met — spread the notes EVENLY across the octaves: no single octave may "
                "hold more than ~45% of the notes. Don't sit in the middle — move whole phrases UP to the high "
                "treble (toward E6/MIDI 88) and DOWN to the deep bass (toward A1/MIDI 33) so every octave in the "
                "range gets comparable use, and dip to <=41 and climb to >=84 somewhere.")
    return f"REQUIREMENT not met — {check}: fix this exactly."


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
            lines.append(_req_fix(c["check"]))
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
            if best is None or _better(rep, best):
                best = rep
            if best["verdict"]:
                break
            # ANCHOR the next round on the BEST draft so far (revise it; don't regenerate from scratch and
            # regress a passing dimension) + the concrete fixes for what that best draft still fails.
            anchor = ("REVISE THE DRAFT BELOW — keep EVERY bar and aspect that already passes, and change ONLY "
                      "what the fixes below require. Do not rewrite from scratch. Your current best draft:\n"
                      + Path(best["path"]).read_text(encoding="utf-8"))
            corrections = [anchor] + feedback(best)
        return best, rounds


def _better(cand, best):
    """cand strictly better than best: pass beats fail; then fewer failed gate checks."""
    if bool(cand["verdict"]) != bool(best["verdict"]):
        return bool(cand["verdict"])
    return cand["score"] < best["score"]


def _strip_prose(p):
    ls = p.read_text().splitlines()
    ki = next((i for i, l in enumerate(ls) if l.strip().startswith("KEY:")), 0)
    if ki > 0:
        p.write_text("\n".join(ls[ki:]) + "\n")
