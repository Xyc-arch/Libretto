#!/usr/bin/env python3
"""probe — the anomaly-detection experiment: a TOOL-FREE reasoner reads a piece (clean or with one injected
anomaly) and must say whether there is an anomaly, where (bar), and what kind. Tool-free = `claude -p` with NO
tools, so the model REASONS about the harmony/key/meter from the grammar text — it cannot compute/extract
(the "probe needs a tool-free reasoner" lesson). Graded vs ground truth, and vs a simple bar-heuristic baseline.

    python -m libretto.tasks.anomaly.probe --cases paper_data/anomaly_v1/cases --model opus --parallel 8

Reports: detection rate (anomalous flagged), false-positive rate (clean flagged), localization (bar ±1),
kind accuracy — for the LLM and for a non-LLM bar-irregularity heuristic.
"""
import argparse
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from libretto.tasks.anomaly.inject import KINDS, _split, _midi
from libretto.tasks.education.measure import scale_pcs

KIND_NAMES = list(KINDS)
_PROMPT = """You are an expert music theorist analysing a piece written as a compact grammar.

Format: a header (KEY, METER, TEMPO), a VOICES line, then bars. Each bar starts `@<n> [chords]` and lists
voice lines `Voice: Pitch@slot>dur` (slot = position in the bar, dur in slots; chords join pitches with +;
`^NN` is velocity).

The piece MAY contain EXACTLY ONE deliberate anomaly — a single spot that breaks music tradition — OR it may
be completely CLEAN. The possible anomaly kinds:
- out_of_key   : a melody note a semitone outside the stated key (a wrong note)
- wrong_bass   : a bass note that is the wrong root under its chord
- dissonance   : a harsh added semitone-cluster tone on a chord (a non-chord tone that clashes)
- meter_glitch : one bar whose note durations overflow the meter (too many beats)

REASON about the key, the harmony bar-by-bar, and the meter. Then respond with ONLY this JSON (no prose):
{"anomaly": true or false, "bar": <bar number or null>, "kind": "<one of out_of_key|wrong_bass|dissonance|meter_glitch or null>", "reason": "<one short sentence>"}

PIECE:
"""


def build_prompt(case_text):
    return _PROMPT + case_text


def _parse(result_text):
    m = re.search(r"\{.*\}", result_text, re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
        return dict(anomaly=bool(d.get("anomaly")), bar=d.get("bar"),
                    kind=(d.get("kind") if d.get("kind") in KIND_NAMES else None), reason=d.get("reason", ""))
    except Exception:
        return None


def run_probe(case_text, model="opus", timeout=180):
    """Tool-free claude -p; returns the parsed verdict dict (or a null verdict on failure)."""
    cmd = ["claude", "-p", build_prompt(case_text), "--allowedTools", "", "--output-format", "json"]
    if model:
        cmd += ["--model", model]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = json.loads(r.stdout or "{}").get("result", "")
        return _parse(out) or dict(anomaly=False, bar=None, kind=None, reason="(unparsed)")
    except Exception as e:  # noqa: BLE001
        return dict(anomaly=False, bar=None, kind=None, reason=f"(error {e!r})")


# ── non-LLM baseline: flag the bar with the largest local irregularity ──────────────────────────────────
def bar_heuristic(case_text):
    """A simple per-bar irregularity detector (NOT the LLM): out-of-key notes + semitone clashes + duration
    overflow. Returns (anomaly_bool, bar, kind) — flags the worst bar if any bar scores > 0."""
    _, pcs, _ = scale_pcs((re.search(r"KEY:\s*([^|]+)", case_text) or [None, "C major"])[1].strip())
    mm = re.search(r"METER:\s*(\d+)/(\d+)", case_text)
    beats = int(mm.group(1)) if mm else 4
    head, bars = _split(case_text)
    best = (0.0, None, None)
    tokre = re.compile(r"((?:[A-G][#b]?-?\d+)(?:\+[A-G][#b]?-?\d+)*)@(\d+)>(\d+)")
    for bi, b in enumerate(bars, 1):
        oob = clash = overflow = 0; maxslot = 0
        for ln in b[1:]:
            if ":" not in ln:
                continue
            for pm_ in tokre.finditer(ln):
                ps, slot, dur = pm_.group(1), int(pm_.group(2)), int(pm_.group(3))
                notes = [n for n in (_midi(x) for x in ps.split("+")) if n is not None]
                oob += sum(1 for n in notes if n % 12 not in pcs)
                s = sorted(notes)
                clash += sum(1 for i in range(len(s) - 1) if s[i + 1] - s[i] == 1)   # semitone cluster
                maxslot = max(maxslot, slot + dur - 1)
        # meter overflow: a note running well past the bar's slot budget (grid ~ 4*beats; be lenient)
        if maxslot > 4 * beats + 6:
            overflow = 1
        score = oob + clash + overflow
        if score > best[0]:
            kind = "meter_glitch" if overflow else ("dissonance" if clash else "out_of_key")
            best = (score, bi, kind)
    return (best[0] > 0, best[1], best[2])


def grade(cases, verdicts):
    """cases: {cid: meta}; verdicts: {cid: {anomaly,bar,kind}}. Returns detection/FP/localization/kind stats."""
    anom = [c for c in cases if cases[c]["has_anomaly"]]
    clean = [c for c in cases if not cases[c]["has_anomaly"]]
    tp = sum(1 for c in anom if verdicts[c]["anomaly"])
    fp = sum(1 for c in clean if verdicts[c]["anomaly"])
    loc = sum(1 for c in anom if verdicts[c]["anomaly"] and verdicts[c].get("bar") is not None
              and abs(int(verdicts[c]["bar"]) - cases[c]["bar"]) <= 1)
    kind_ok = sum(1 for c in anom if verdicts[c]["anomaly"] and verdicts[c].get("kind") == cases[c]["kind"])
    return dict(n_anom=len(anom), n_clean=len(clean),
                detection=tp, detection_rate=round(tp / max(1, len(anom)), 2),
                false_pos=fp, false_pos_rate=round(fp / max(1, len(clean)), 2),
                localized=loc, localized_rate=round(loc / max(1, len(anom)), 2),
                kind_correct=kind_ok, kind_rate=round(kind_ok / max(1, len(anom)), 2))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cases", default="paper_data/anomaly_v1/cases")
    ap.add_argument("--model", default="opus")
    ap.add_argument("--parallel", type=int, default=8)
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    C = Path(a.cases); cases = json.loads((C / "cases.json").read_text())
    texts = {cid: (C / f"{cid}.txt").read_text() for cid in cases}

    # LLM probe (parallel, tool-free)
    llm = {}
    print(f"probing {len(cases)} cases with {a.model} (tool-free, {a.parallel} parallel)...", flush=True)
    with ThreadPoolExecutor(max_workers=a.parallel) as pool:
        futs = {pool.submit(run_probe, texts[cid], a.model): cid for cid in cases}
        for f in as_completed(futs):
            cid = futs[f]; llm[cid] = f.result()
            gt = cases[cid]
            print(f"  {cid:30s} truth={'ANOM('+gt['kind']+' b'+str(gt['bar'])+')' if gt['has_anomaly'] else 'clean':<22} "
                  f"llm={'ANOM(' + str(llm[cid]['kind']) + ' b' + str(llm[cid]['bar']) + ')' if llm[cid]['anomaly'] else 'clean'}", flush=True)

    # non-LLM baseline
    base = {}
    for cid in cases:
        an, bar, kind = bar_heuristic(texts[cid])
        base[cid] = dict(anomaly=an, bar=bar, kind=kind)

    gl = grade(cases, llm); gb = grade(cases, base)
    print("\n=== RESULTS ===")
    print(f"{'metric':<22}{'LLM ('+a.model+')':>16}{'heuristic':>12}")
    for k, lbl in [("detection_rate", "detection"), ("false_pos_rate", "false-positive"),
                   ("localized_rate", "localization ±1"), ("kind_rate", "kind accuracy")]:
        print(f"{lbl:<22}{gl[k]:>16}{gb[k]:>12}")
    print(f"(anomalous n={gl['n_anom']}, clean n={gl['n_clean']})")
    if a.out:
        Path(a.out).write_text(json.dumps(dict(model=a.model, llm=gl, heuristic=gb,
                               verdicts={cid: dict(truth=cases[cid], llm=llm[cid], heuristic=base[cid]) for cid in cases}), indent=2))
        print(f"-> {a.out}")


if __name__ == "__main__":
    main()
