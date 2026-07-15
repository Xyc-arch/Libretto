#!/usr/bin/env python3
"""batch.py — Dockerized ACCOMPANIMENT loop, PARALLEL. Give an agent a piece with one instrument track MASKED
and have it compose the missing track; splice it back and grade the completed piece.

For each case (role-balanced bass/drums/harmony): show the CONTEXT (piece minus the target voice) + the role/
instrument to add -> a Claude Code agent (claude -p) writes ONLY that voice's track -> `measure.grade` splices
it in and scores proximity-to-original (bass/harmony) or groove-fit (drums) -> feedback -> keep the best. Same
claude -p / BYO-auth harness as the gaptask + morph loops.

    python -m libretto.tasks.accompaniment.loop.batch --parallel 11 --rounds 3 --model opus
"""
import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

PROJ = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJ))

from libretto.generation.interface import PROMPTS                              # noqa: E402
from libretto.tasks.accompaniment.measure import grade                         # noqa: E402
from libretto.tasks.newgen.loop.generator import ClaudeCodeGenerator           # noqa: E402
from libretto.tasks.newgen.loop.runlog import RunLog                           # noqa: E402
import re                                                                       # noqa: E402

CASES = Path(os.environ.get("ACCOMP_CASES") or (PROJ / "paper_data/accompaniment_v1/cases"))
STATE = Path(os.environ.get("ACCOMP_STATE") or (PROJ / "accompaniment_loop" / "state"))
SHARED = (PROMPTS / "_shared.md").read_text()
LOG = None

ROLE_BRIEF = {
    "bass": "a BASS line — mostly roots/fifths of the implied chords, locking with the rhythm, one note at a time.",
    "drums": "a DRUM KIT groove — use GM drum pitches (C2=36 kick, D2=38 snare, F#2=42 hat), lock to the meter "
             "with a steady backbeat (snare on 2 & 4 in 4/4).",
    "harmony": "a HARMONY/comping part — chords (join pitches with +) that voice the implied progression, "
               "in a mid register, rhythmically supporting the other parts.",
}


def _hv(text, tag):
    m = re.search(rf"{tag}:\s*([^|]+)", text)
    return m.group(1).strip() if m else ""


def build_prompt(case, ctx_text, corrections=None):
    role, voice = case["role"], case["voice"]
    vtag = f"{voice}[drums]" if role == "drums" else voice   # drums MUST be tagged so it renders on the kit channel
    context = dict(add_role=role, instrument_voice=vtag, key=_hv(ctx_text, "KEY"),
                   meter=_hv(ctx_text, "METER"), tempo=_hv(ctx_text, "TEMPO"), context_grammar=ctx_text)
    drum_note = (" The header voice MUST be tagged `[drums]` (i.e. `VOICES: " + vtag + "`) or it will not play as "
                 "a kit; use GM drum pitches (C2/36 kick, D2/38 snare, F#2/42 closed hat, A#2/46 open hat)."
                 if role == "drums" else "")
    obj = (f"The piece below is MISSING its {role} track. Compose {ROLE_BRIEF[role]}\n"
           f"Output ONLY that ONE voice as grammar: a header line, `VOICES: {vtag}`, then bars `@N` each with "
           f"a single `{voice}:` line of notes (Pitch@slot>dur[^vel]) that FIT the context's harmony, key "
           f"({_hv(ctx_text, 'KEY')}), meter and groove. Same number of bars as the context.{drum_note} Do NOT "
           f"rewrite the other parts — output only the {voice} track.")
    p = (f"# Accompaniment — complete the missing {role} track\n\n{SHARED}\n\n## OBJECTIVE\n{obj}\n\n"
         f"## CONTEXT (JSON)\n```json\n{json.dumps(context, indent=1)}\n```\n")
    if corrections:
        p += "\n## CORRECTIONS — act on ALL, regenerate the whole track\n" + "\n".join(corrections)
    return p


def _feedback(g):
    lines = []
    if g["role"] == "drums":
        if not g.get("groove_fit"):
            if len(g.get("kit", [])) < 2:
                lines.append(f"KIT: use a fuller kit — you have {g.get('kit')}; include kick (C2), snare (D2) "
                             f"AND hi-hat (F#2).")
            if g.get("rhythm_sim", 0) < 0.5:
                lines.append("GROOVE: lock the pattern to the meter — steady hats, kick on the downbeats, "
                             "snare on the backbeat (2 & 4).")
    else:
        if g["in_key_frac"] < 0.8:
            lines.append(f"KEY: {g['in_key_frac']:.0%} of your notes are in key — stay in the key/harmony.")
        if not g["improved"]:
            lines.append("FIT: your track does not make the piece sit closer to a coherent whole — match the "
                         "implied chords and register more closely.")
        if g["n_notes"] < 4:
            lines.append("CONTENT: write a real, active part across the whole piece (not a few notes).")
    if g["copy_vs_answer"] > 0.6:
        lines.append("NOVELTY: invent your own fitting part — do not transcribe an obvious existing line.")
    return lines


def _score(g):
    """Higher = better. proximity: beat% (+improved); drums: rhythm_sim + kit + fit."""
    if g["role"] == "drums":
        return (1 if g.get("groove_fit") else 0, g.get("rhythm_sim", 0), len(g.get("kit", [])))
    return (1 if g["fit"] else 0, g["beat_pct"], 1 if g["improved"] else 0)


def _run_one(job, gen, rounds):
    cid, case = job
    ctx = (CASES / case["context"]).read_text()
    ans = (CASES / case["answer"]).read_text()
    case = dict(case, answer_text=ans)
    if case.get("original"):
        case["original_text"] = (CASES / case["original"]).read_text()
    wd = STATE / cid; wd.mkdir(parents=True, exist_ok=True)
    mj = wd / "grade.json"
    if mj.exists():
        try:
            g = json.loads(mj.read_text())
            print(f"[{cid}] resume: graded (fit={g.get('fit')}) — skip", flush=True)
            return dict(case=cid, **_summ(g))
        except Exception:  # noqa: BLE001
            pass
    corrections, best, best_key = [], None, None
    for r in range(1, rounds + 1):
        try:
            track = gen.generate(build_prompt(case, ctx, corrections), {})
        except Exception as e:  # noqa: BLE001
            print(f"[{cid}] round {r}: generate FAILED ({e!r})", flush=True); track = ""
        p = wd / f"r{r}.txt"; p.write_text(track or "", encoding="utf-8")
        try:
            g = grade(ctx, track or "", case)
        except Exception:  # noqa: BLE001
            g = dict(role=case["role"], voice=case["voice"], beat_pct=0, fit=False, improved=False,
                     n_notes=0, in_key_frac=0.0, copy_vs_answer=0.0)
        k = _score(g)
        if best is None or k > best_key:
            best, best_key = dict(path=str(p), **g), k
        if LOG:
            LOG.event("round", case=cid, role=case["role"], round=r, fit=g.get("fit"),
                      beat=g.get("beat_pct"), groove=g.get("groove_fit"))
        print(f"[{cid}] round {r}: role {case['role']} fit={g.get('fit')} "
              f"{'groove_sim ' + str(g.get('rhythm_sim')) if case['role'] == 'drums' else 'beat% ' + str(g.get('beat_pct'))}",
              flush=True)
        if g.get("fit"):
            break
        corrections = _feedback(g)
    (wd / "best.txt").write_text(Path(best["path"]).read_text(encoding="utf-8"))
    bc = {kk: v for kk, v in best.items() if kk != "path"}
    mj.write_text(json.dumps(bc, indent=2, default=str))
    print(f"[{cid}] BEST role {case['role']} fit={best.get('fit')}", flush=True)
    return dict(case=cid, **_summ(best))


def _summ(g):
    return dict(role=g.get("role"), fit=bool(g.get("fit")), beat_pct=g.get("beat_pct"),
                groove_fit=g.get("groove_fit"), rhythm_sim=g.get("rhythm_sim"), improved=g.get("improved"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--parallel", type=int, default=11)
    ap.add_argument("--model", default="opus")
    ap.add_argument("--timeout", type=int, default=0)
    a = ap.parse_args()
    cases = json.loads((CASES / "cases.json").read_text())
    if a.cases:
        want = {c.strip() for c in a.cases.split(",")}
        cases = {k: v for k, v in cases.items() if k in want}
    STATE.mkdir(parents=True, exist_ok=True)
    global LOG
    LOG = RunLog(STATE, model=a.model, proj=PROJ, params=dict(n=len(cases), rounds=a.rounds, parallel=a.parallel))
    print(f"{len(cases)} accompaniment cases | {a.parallel} parallel | rounds<= {a.rounds} | model {a.model}", flush=True)
    gen = ClaudeCodeGenerator(model=a.model, timeout_s=(a.timeout or None))
    manifest = []

    def _safe(job):
        try:
            return _run_one(job, gen, a.rounds)
        except Exception as e:  # noqa: BLE001
            print(f"[{job[0]}] CASE FAILED: {e!r}", flush=True); return None

    with ThreadPoolExecutor(max_workers=a.parallel) as pool:
        for f in as_completed([pool.submit(_safe, j) for j in cases.items()]):
            m = f.result()
            if m is not None:
                manifest.append(m)

    import statistics as st
    from collections import Counter
    fits = sum(1 for m in manifest if m["fit"])
    by_role = {r: [m for m in manifest if m["role"] == r] for r in ("bass", "drums", "harmony")}
    summary = dict(n=len(manifest), fit=fits,
                   fit_by_role={r: f"{sum(1 for m in v if m['fit'])}/{len(v)}" for r, v in by_role.items() if v},
                   mean_beat_pct=round(st.mean([m["beat_pct"] for m in manifest if m.get("beat_pct") is not None
                                                and m["role"] != "drums"]), 1) if manifest else None)
    (STATE / "accomp_manifest.json").write_text(json.dumps({**summary, "runs": manifest}, indent=2))
    LOG.close(summary=summary)
    print(f"\nDONE: {len(manifest)} | fit {fits}/{len(manifest)} | by role {summary['fit_by_role']} -> {STATE}")


if __name__ == "__main__":
    main()
