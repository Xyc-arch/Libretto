#!/usr/bin/env python3
"""build_cases — reproducible case builder for the ACCOMPANIMENT task (reconstruct a removed instrument track).

Reads coherent multi-voice corpus songs READ-ONLY and writes, to a SEPARATE dir (never touching the corpus),
cases that MASK one whole instrument voice: `<cid>_context.txt` (the piece with that voice removed — what the
agent sees) and `<cid>_answer.txt` (the removed voice alone — the held-out ground truth). The target voice
rotates across ROLES (bass / drums / harmony) so the set is role-balanced. Reproducible by seed.

    python -m libretto.tasks.accompaniment.build_cases --n 20 --seed 1 --out paper_data/accompaniment_v1/cases

Grading (measure.py) splices a generated voice back into the context and checks how close the COMPLETED piece
sits to the ORIGINAL (fingerprint beat%) + role/fit + non-copy.
"""
import argparse
import json
import re
from pathlib import Path

import libretto

DATA = libretto.data_root()
GRAMMAR = DATA / "grammar"
DEFAULT_OUT = "paper_data/accompaniment_v1/cases"
BARS_RANGE = (48, 200)
ROLES = ["bass", "drums", "harmony"]     # accompaniment roles we mask (not the lead melody)


def _split(text):
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


def _voices(head):
    """[(name, prog, is_drum)] from the VOICES header line."""
    line = next((l for l in head if l.startswith("VOICES:")), "")
    out = []
    for v in line.split(":", 1)[1].split(",") if ":" in line else []:
        name = v.split("[")[0].strip()
        prog = re.search(r"prog=(\d+)", v)
        out.append((name, int(prog.group(1)) if prog else None, "[drums]" in v))
    return out


def _role(name, prog, is_drum, plays_chords):
    if is_drum:
        return "drums"
    if "bass" in name.lower() or (prog is not None and 32 <= prog <= 39):
        return "bass"
    return "harmony" if plays_chords else "melody"


def _voice_line(bar_line):
    return bar_line.partition(":")[0].strip() if ":" in bar_line else None


def remove_voice(text, target):
    """Return (context_text, answer_text): the piece with voice `target` dropped, and the voice alone (with bar
    markers for timing). PURE — does not mutate `text`."""
    head, bars = _split(text)
    vline = next((l for l in head if l.startswith("VOICES:")), "")
    specs = [v.strip() for v in vline.split(":", 1)[1].split(",")] if ":" in vline else []
    kept = [v for v in specs if v.split("[")[0].strip() != target]
    # keep the target's FULL spec (its [drums] / [prog=N] tag) so the held-out voice renders on the right
    # channel — dropping it makes a [drums] track decode as a melodic instrument (silent/wrong in the mix).
    target_full = next((v for v in specs if v.split("[")[0].strip() == target), target)
    ctx_head = [(("VOICES: " + ", ".join(kept)) if l.startswith("VOICES:") else l) for l in head]
    ans_head = [(f"VOICES: {target_full}" if l.startswith("VOICES:") else l) for l in head]
    ctx_bars, ans_bars = [], []
    for b in bars:
        marker = b[0]
        ctx_bars.append([marker] + [l for l in b[1:] if _voice_line(l) != target])
        ans_bars.append([marker] + [l for l in b[1:] if _voice_line(l) == target])
    join = lambda h, bb: "\n".join(h + [x for bl in bb for x in bl]) + "\n"
    return join(ctx_head, ctx_bars), join(ans_head, ans_bars)


def _excerpt(text, bars, seed):
    """A contiguous window of `bars` bars from the interior, all voices kept, renumbered @1.. Pure."""
    import random
    head, blocks = _split(text)
    if len(blocks) <= bars:
        return text
    lo = random.Random(seed).randint(2, len(blocks) - bars - 2)
    win = [list(b) for b in blocks[lo:lo + bars]]
    for i, b in enumerate(win, 1):
        b[0] = re.sub(r"^@\d+", f"@{i}", b[0])
    out_head = [re.sub(r"BARS:\s*\d+", f"BARS: {bars}", head[0])] + head[1:] if head else []
    return "\n".join(out_head + [x for b in win for x in b]) + "\n"


def build_cases(n=20, seed=1, out=DEFAULT_OUT, excerpt_bars=0):
    """Build n role-balanced accompaniment cases. Returns cases dict. Pure wrt the corpus. excerpt_bars>0 uses
    a short window as the context (tractable generation, cheaper) and stores the windowed ORIGINAL as the
    grading reference."""
    import numpy as np
    truth = json.loads((DATA / "answer_key" / "grammar_truth.json").read_text())

    def bars_of(sid):
        b = truth.get(sid, {}).get("bars"); return int(b) if str(b).isdigit() else 0

    outp = Path(out); outp.mkdir(parents=True, exist_ok=True)
    eligible = sorted(s for s in truth if BARS_RANGE[0] <= bars_of(s) <= BARS_RANGE[1]
                      and (GRAMMAR / f"{s}.txt").exists())
    rng = np.random.RandomState(seed)
    if seed > 0:
        eligible = list(eligible); rng.shuffle(eligible)
    cases = {}
    used = 0
    for sid in eligible:
        if used >= n:
            break
        text = (GRAMMAR / f"{sid}.txt").read_text()          # READ-ONLY
        if excerpt_bars:
            text = _excerpt(text, excerpt_bars, seed * 100 + used)   # a copy — corpus untouched
        head, _ = _split(text)
        vs = _voices(head)
        if len(vs) < 3:
            continue
        plays_chords = {name: (f"{name}:" in text and "+" in text) for name, _, _ in vs}  # coarse
        want = ROLES[used % len(ROLES)]
        lines_of = lambda name: [l for l in text.splitlines() if l.strip().startswith(name + ":")]
        # candidate voices of the wanted role that actually have notes
        cand = [name for name, prog, drum in vs
                if _role(name, prog, drum, "+" in "".join(lines_of(name))) == want and lines_of(name)]
        if want == "drums":
            # prefer a FULL KIT (has kick C2/B1 = 35/36 AND snare D2/Eb2 = 38/40) over aux percussion
            def full_kit(name):
                import pretty_midi as pm
                ms = set()
                for l in lines_of(name):
                    for tok in re.findall(r"([A-G][#b]?-?\d+)@", l):
                        try:
                            ms.add(pm.note_name_to_number(tok))
                        except Exception:
                            pass
                return (ms & {35, 36}) and (ms & {37, 38, 40})
            cand = [n for n in cand if full_kit(n)]     # drum cases must be a real kit (kick + snare)
        target = cand[0] if cand else None
        if target is None:
            continue
        ctx, ans = remove_voice(text, target)
        # need real content in the answer and >=2 remaining context voices
        if sum(1 for l in ans.splitlines() if l.strip().startswith(target + ":")) < 4 or len(vs) - 1 < 2:
            continue
        cid = f"{sid}__{want}"
        (outp / f"{cid}_context.txt").write_text(ctx)
        (outp / f"{cid}_answer.txt").write_text(ans)
        entry = dict(sid=sid, genre=truth[sid].get("genre"), role=want, voice=target,
                     context=f"{cid}_context.txt", answer=f"{cid}_answer.txt", n_context_voices=len(vs) - 1)
        if excerpt_bars:
            (outp / f"{cid}_original.txt").write_text(text)   # windowed full piece = grading reference
            entry["original"] = f"{cid}_original.txt"
        cases[cid] = entry
        used += 1
    (outp / "cases.json").write_text(json.dumps(cases, indent=2))
    return cases


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--excerpt-bars", type=int, default=0, help="short N-bar context (0 = whole song)")
    a = ap.parse_args()
    cases = build_cases(n=a.n, seed=a.seed, out=a.out, excerpt_bars=a.excerpt_bars)
    from collections import Counter
    print(f"built {len(cases)} accompaniment cases -> {a.out}")
    print("roles:", dict(Counter(c["role"] for c in cases.values())))


if __name__ == "__main__":
    main()
