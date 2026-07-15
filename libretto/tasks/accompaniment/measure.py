#!/usr/bin/env python3
"""measure — grade an accompaniment completion: splice the generated instrument track back into the context
and measure how close the COMPLETED piece sits to the ORIGINAL (fingerprint beat% vs chance), plus fit (the
added voice is in-key, non-degenerate, has real content) and non-copy of the held-out real track.

`splice(context, voice_text, voice_name)` re-inserts a voice; `grade(...)` returns the numbers. Reuses the
gaptask 39-axis fingerprint (fp/dist/corpus beat%) — a good completion makes the whole piece look like the
original again.
"""
import re
import tempfile
from pathlib import Path

import libretto
from libretto.tasks.gaptask.refine_loop import fp, dist, _corpus_fp
from libretto.tasks.accompaniment.build_cases import _split
from libretto.core import copy_risk
from libretto.tasks.education.measure import scale_pcs

DATA = libretto.data_root()
GRAMMAR = DATA / "grammar"


def _voice_bar_lines(voice_text, voice_name):
    """{bar_index (1-based): [voice lines]} for `voice_name` from a voice-only grammar (answer or generated)."""
    _, bars = _split(voice_text)
    out = {}
    for bi, b in enumerate(bars, 1):
        lines = [l for l in b[1:] if l.partition(":")[0].strip() == voice_name]
        if lines:
            out[bi] = lines
    return out


def splice(context_text, voice_text, voice_name):
    """Re-insert `voice_name`'s bar lines (from voice_text) into the context, and add it back to VOICES."""
    head, bars = _split(context_text)
    vmap = _voice_bar_lines(voice_text, voice_name)
    new_head = [(l + (f", {voice_name}" if not l.rstrip().endswith(voice_name) else "")
                 if l.startswith("VOICES:") else l) for l in head]
    out = list(new_head)
    for bi, b in enumerate(bars, 1):
        out.extend(b)
        out.extend(vmap.get(bi, []))
    return "\n".join(out) + "\n"


def _fp_text(text):
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write(text); p = f.name
    try:
        return fp(p)
    finally:
        Path(p).unlink(missing_ok=True)


_KICK = {35, 36}
_SNARE = {37, 38, 40}
_HAT_CYM = {42, 44, 46, 49, 51, 52, 55, 57, 59}
_TOK_SLOT = re.compile(r"([A-G][#b]?-?\d+)@(\d+)>(\d+)")


def _drum_onsets(voice_text, voice_name):
    """[(bar_index, slot, midi)] for a drum voice (grammar drum pitches = GM drum note numbers)."""
    import pretty_midi as pm
    _, bars = _split(voice_text)
    out = []
    for bi, b in enumerate(bars, 1):
        for l in b[1:]:
            if l.partition(":")[0].strip() != voice_name:
                continue
            for m in _TOK_SLOT.finditer(l):
                for nn in m.group(1).split("+"):
                    try:
                        out.append((bi, int(m.group(2)), pm.note_name_to_number(nn)))
                    except Exception:
                        pass
    return out


def _bar_slots_text(text):
    """Estimate slots-per-bar from a filled piece, as the median per-bar max slot."""
    import statistics as st
    _, bars = _split(text)
    maxes = []
    for b in bars:
        s = [int(m.group(2)) + int(m.group(3)) - 1 for l in b[1:] for m in _TOK_SLOT.finditer(l)]
        if s:
            maxes.append(max(s))
    return max(4, int(st.median(maxes))) if maxes else 16


def drum_groove(generated_voice_text, real_voice_text, voice_name, bar_slots, n_bars):
    """Rhythm-based fit for a DRUM track (pitch fingerprint ~ignores drums): kit coverage + density + how
    similar the onset-position groove is to the real track. Returns metrics + groove_fit."""
    import math
    g = _drum_onsets(generated_voice_text, voice_name)
    r = _drum_onsets(real_voice_text, voice_name)
    kit = set()
    for _, _, m in g:
        if m in _KICK: kit.add("kick")
        elif m in _SNARE: kit.add("snare")
        elif m in _HAT_CYM: kit.add("hat")
    dens_g = len(g) / max(1, n_bars)
    dens_r = len(r) / max(1, n_bars)

    def hist(onsets, bins=16):
        h = [0.0] * bins
        for _, slot, _ in onsets:
            h[min(bins - 1, int((slot % bar_slots) / bar_slots * bins))] += 1
        s = sum(h) or 1.0
        return [x / s for x in h]

    hg, hr = hist(g), hist(r)
    dot = sum(a * b for a, b in zip(hg, hr))
    mag = math.sqrt(sum(a * a for a in hg)) * math.sqrt(sum(b * b for b in hr))
    sim = round(dot / mag, 3) if mag else 0.0
    dratio = dens_g / dens_r if dens_r else 0.0
    fit = len(kit) >= 2 and 0.4 <= dratio <= 2.5 and sim >= 0.5
    return dict(kit=sorted(kit), density=round(dens_g, 1), density_real=round(dens_r, 1),
                rhythm_sim=sim, groove_fit=bool(fit))


def grade(context_text, generated_voice_text, case):
    """Grade a completion. `case` carries sid, role, voice, answer(text or path). Returns the metrics dict."""
    sid, voice = case["sid"], case["voice"]
    completed = splice(context_text, generated_voice_text, voice)
    # grading reference = the windowed ORIGINAL (excerpt cases) or the full corpus song
    fpo = _fp_text(case["original_text"]) if case.get("original_text") else fp(str(GRAMMAR / f"{sid}.txt"))
    fpc = _fp_text(completed)                        # context + generated voice
    fpctx = _fp_text(context_text)                   # context alone (no accompaniment track)
    d_completed = dist(fpc, fpo)
    d_context = dist(fpctx, fpo)                      # how far the piece is WITHOUT the track
    cfps = _corpus_fp()
    chances = sorted(dist(fpo, cfps[s]) for s in cfps)
    beat = round(sum(1 for dd in chances if dd > d_completed) / len(chances) * 100)
    # did adding the track help (move toward original)?
    improved = d_completed < d_context
    # fit: the generated voice has real content, is in-key, not a verbatim copy of the held-out real track
    gen_lines = [l for l in generated_voice_text.splitlines() if l.partition(":")[0].strip() == voice]
    n_notes = sum(len(re.findall(r"@\d+>", l)) for l in gen_lines)
    key = (re.search(r"KEY:\s*([^|]+)", context_text) or [None, "C major"])[1].strip()
    _, pcs, _ = scale_pcs(key)
    gen_pitch = [x for l in gen_lines for x in re.findall(r"([A-G][#b]?-?\d+)", l)]
    import pretty_midi as pm
    inkey = [pm.note_name_to_number(x) % 12 in pcs for x in gen_pitch if _safe(x)]
    in_key_frac = round(sum(inkey) / len(inkey), 2) if inkey else 0.0
    cr = copy_risk(_write_tmp(generated_voice_text), ref=_write_answer(case), vs_corpus=False) \
        if case.get("answer_text") else {"ref": {}}
    copy = cr.get("ref", {}).get("overlap_slid", 0.0)
    out = dict(role=case["role"], voice=voice, beat_pct=beat, d_completed=round(d_completed, 1),
               d_context=round(d_context, 1), improved=bool(improved), n_notes=n_notes,
               in_key_frac=in_key_frac, copy_vs_answer=round(float(copy), 3))
    if case["role"] == "drums":
        # pitch fingerprint ~ignores percussion; grade the GROOVE instead (kit + density + onset-position sim)
        n_bars = len(_split(context_text)[1])
        ref = case.get("original_text") or (GRAMMAR / f"{sid}.txt").read_text()
        bs = _bar_slots_text(ref)
        gr = drum_groove(generated_voice_text, case.get("answer_text", ""), voice, bs, n_bars)
        out.update(gr)
        out["fit"] = bool(gr["groove_fit"])
        out["score_metric"] = "groove"
    else:
        out["fit"] = bool(n_notes >= 4 and in_key_frac >= 0.8)
        out["score_metric"] = "proximity"
    return out


def _safe(nn):
    import pretty_midi as pm
    try:
        pm.note_name_to_number(nn); return True
    except Exception:
        return False


def _write_tmp(text):
    f = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False); f.write(text); f.close(); return f.name


def _write_answer(case):
    return _write_tmp(case["answer_text"])


if __name__ == "__main__":
    import argparse
    import json
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="paper_data/accompaniment_v1/cases")
    ap.add_argument("--oracle", action="store_true", help="grade the REAL answer track (sanity: beat% high)")
    a = ap.parse_args()
    C = Path(a.cases); cases = json.loads((C / "cases.json").read_text())
    if a.oracle:
        import statistics as st
        beats = []
        for cid, c in cases.items():
            ctx = (C / c["context"]).read_text(); ans = (C / c["answer"]).read_text()
            c = dict(c, answer_text=ans)
            if c.get("original"):
                c["original_text"] = (C / c["original"]).read_text()
            g = grade(ctx, ans, c)
            beats.append(g["beat_pct"])
            print(f"  {cid:26s} {c['role']:8s} beat% {g['beat_pct']:>3} (d {g['d_completed']} vs ctx {g['d_context']}) "
                  f"improved={g['improved']} copy={g['copy_vs_answer']}")
        print(f"\nORACLE mean beat% {round(st.mean(beats), 1)} (splicing the REAL track back should score high)")
