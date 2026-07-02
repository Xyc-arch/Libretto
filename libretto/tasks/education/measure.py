#!/usr/bin/env python3
"""measure.py — verify a generated practice piece.

Four gate criteria for an education practice piece:
  SINGLE-CHANNEL  exactly one voice (piano).
  IN-KEY          notes belong to the requested key/scale (a small chromatic allowance for the device).
  CHALLENGE       the required concept(s) are actually exercised (per-category detectors).
  NOVEL           copy-control: copy_risk vs the corpus < CORPUS_THR AND overlap vs the SHOWN grammars
                  (the kb_theory examples + classical exemplar) < SHOWN_THR — so the drill is genuinely new,
                  not a transcription of the textbook snippet it was shown.
"""
import re
import statistics
import tempfile
from collections import Counter
from pathlib import Path

from libretto.core import Song
from libretto.core.copy_risk import piece_notes, slide_overlap, copy_risk
from . import retrieval as R

# Copy control = two signals. The PRIMARY novelty gate is SHOWN_THR (did the piece reproduce the kb_theory
# example / classical exemplar it was handed). CORPUS_THR is a loose backstop catching only outright real-song
# duplicates: it is GROUNDED — real SHORT single-voice excerpts (12-bar top-lines of corpus songs) score
# copy_vs_corpus median 0.39 / p75 0.45 / p90 0.70 against the rest of the corpus, because short diatonic
# pedagogical material inherently shares stock notes. So the from-scratch 0.30 bound does not apply here; the
# backstop is set at that p90 (0.70). Novelty for a drill = "not a transcription of what you were shown",
# which SHOWN_THR enforces strictly.
SHOWN_THR = 0.50         # vs the kb example / classical exemplar it was shown — the real novelty gate
CORPUS_THR = 0.70        # vs real songs — loose backstop (grounded: p90 of real short single-voice excerpts)
CHROMATIC_ALLOWANCE = 0.12   # fraction of notes allowed outside the scale (for passing tones / the device)

NOTE_PC = {'C': 0, 'C#': 1, 'DB': 1, 'D': 2, 'D#': 3, 'EB': 3, 'E': 4, 'FB': 4, 'F': 5, 'E#': 5,
           'F#': 6, 'GB': 6, 'G': 7, 'G#': 8, 'AB': 8, 'A': 9, 'A#': 10, 'BB': 10, 'B': 11, 'CB': 11}
SCALES = {
    'major': [0, 2, 4, 5, 7, 9, 11], 'ionian': [0, 2, 4, 5, 7, 9, 11],
    'minor': [0, 2, 3, 5, 7, 8, 10], 'natural minor': [0, 2, 3, 5, 7, 8, 10], 'aeolian': [0, 2, 3, 5, 7, 8, 10],
    'harmonic minor': [0, 2, 3, 5, 7, 8, 11], 'melodic minor': [0, 2, 3, 5, 7, 9, 11],
    'major pentatonic': [0, 2, 4, 7, 9], 'minor pentatonic': [0, 3, 5, 7, 10],
    'blues': [0, 3, 5, 6, 7, 10], 'chromatic': list(range(12)), 'whole tone': [0, 2, 4, 6, 8, 10],
    'dorian': [0, 2, 3, 5, 7, 9, 10], 'phrygian': [0, 1, 3, 5, 7, 8, 10], 'lydian': [0, 2, 4, 6, 7, 9, 11],
    'mixolydian': [0, 2, 4, 5, 7, 9, 10], 'locrian': [0, 1, 3, 5, 6, 8, 10],
}
BEATS_ONSET = {0.0, 1.0, 2.0, 3.0}   # on-beat positions (0-indexed beats); off-beat = anything else


def scale_pcs(key):
    toks = key.replace('♭', 'b').replace('♯', '#').split()
    tonic = toks[0].strip().upper()
    tonic_pc = NOTE_PC.get(tonic, NOTE_PC.get(tonic[0], 0))
    mode = " ".join(toks[1:]).lower().strip() or "major"
    iv = SCALES.get(mode, SCALES["major"])
    return tonic_pc, set((tonic_pc + i) % 12 for i in iv), mode


# ---- challenge detectors: each returns (passed, detail) given the parsed song + grammar text ----
def _beat_unit(meter):
    """Beat unit in quarter-beats from the meter denominator: 4/4->1.0, 3/4->1.0, 6/8->0.5 (compound)."""
    try:
        return 4.0 / int(str(meter).split("/")[1])
    except Exception:
        return 1.0


def _offbeat_ratio(events, beat_unit=1.0):
    """Fraction of onsets that fall OFF the meter's beat grid (meter-aware: in 6/8 the eighths are on-pulse)."""
    if not events:
        return 0.0
    return sum(1 for e in events if round((e["onb"] / beat_unit) % 1.0, 3) not in (0.0,)) / len(events)


def _durations(events):
    return [round(e["dur"], 3) for e in events]


def _toplines(events):
    by_on = {}
    for e in events:
        by_on.setdefault(round(e["onb"] + (e["bar"] - 1) * 100, 3), []).append(e["midi"])
    return [max(v) for _, v in sorted(by_on.items())]


def _melodic_intervals(events):
    tops = _toplines(events)
    return [abs(b - a) for a, b in zip(tops, tops[1:])]


def _signed_intervals(events):
    tops = _toplines(events)
    return [b - a for a, b in zip(tops, tops[1:])]


def _max_simultaneity(events):
    cnt = {}
    for e in events:
        k = (e["bar"], round(e["onb"], 3))
        cnt[k] = cnt.get(k, 0) + 1
    return max(cnt.values()) if cnt else 0


def detect_challenge(cid, events, grammar_text, beat_unit=1.0):
    """Return (check_label, passed, detail). Dispatch by the concept's category/id."""
    e = R.concept(cid); cat = e["category"]; durs = _durations(events)
    if cid in ("TR-SYNCOPATION", "TR-PAT-SYNCOPATED-RHYTHM"):
        r = _offbeat_ratio(events, beat_unit); return (f"syncopation off-beat ratio {r:.2f}≥0.30", r >= 0.30, r)
    if cid in ("TR-TRIPLET", "TR-PAT-TRIPLET-RHYTHM", "TR-METER-128"):
        has = "grid:12t" in grammar_text; return ("triplet/12t bars present", has, has)
    if cid == "TR-EIGHTH-NOTE" or cid == "TR-PAT-FOUR-EIGHTHS":
        has = any(abs(d - 0.5) < 0.05 for d in durs); return ("eighth-notes present", has, has)
    if cid == "TR-SIXTEENTH-NOTE" or cid == "TR-PAT-SIXTEENTH-RUN":
        has = any(abs(d - 0.25) < 0.05 for d in durs); return ("sixteenth-notes present", has, has)
    if cid in ("TR-WHOLE-NOTE",):
        has = any(d >= 3.5 for d in durs); return ("whole-note present", has, has)
    if cid in ("TR-DOTTED-NOTE", "TR-PAT-DOTTED-LONG-SHORT", "TR-PAT-DOTTED-SHORT-LONG"):
        has = any(abs(d - 1.5) < 0.05 or abs(d - 0.75) < 0.05 for d in durs); return ("dotted rhythm present", has, has)
    if cid in ("TR-TIE",):
        # a tie = a note sustained ACROSS a beat line (sounding through the next beat). Meter-aware; a plain
        # on-beat quarter (ends exactly on the next beat) is NOT a tie — only notes that cross the boundary.
        import math
        held = False
        for e in events:
            start = e["onb"]; end = start + e["dur"]
            nb = (math.floor(round(start / beat_unit, 6)) + 1) * beat_unit
            if start < nb < end - 1e-6:
                held = True; break
        return ("tie / note sustained across a beat present", held, held)
    if cat == "scale" or cat == "key":
        return ("(scale handled by IN-KEY check)", True, None)
    if cat == "chord" or cat == "progression" or cat == "cadence":
        # harmony present as a BLOCK chord OR an arpeggiated chord outline (>=3 distinct pcs within a bar)
        sim = _max_simultaneity(events)
        barpcs = {}
        for e in events:
            barpcs.setdefault(e["bar"], set()).add(e["midi"] % 12)
        maxpcs = max((len(v) for v in barpcs.values()), default=0)
        ok = sim >= 3 or maxpcs >= 3
        return (f"harmony present (block sim {sim} or {maxpcs} pcs/bar ≥3)", ok, dict(sim=sim, pcs=maxpcs))
    if cid in ("TM-LEAP",):
        iv = _melodic_intervals(events); has = any(i >= 3 for i in iv)
        return (f"melodic leap present (max {max(iv) if iv else 0})", has, max(iv) if iv else 0)
    if cid in ("TM-STEPWISE",):
        iv = _melodic_intervals(events); frac = sum(1 for i in iv if i <= 2) / max(1, len(iv))
        return (f"stepwise fraction {frac:.2f}≥0.6", frac >= 0.6, frac)
    if cid in ("TX-ARPEGGIO", "TX-BROKEN-CHORDS", "TX-ALBERTI-BASS"):
        # broken/arpeggiated figuration = a chord SPREAD across a bar (a bar with >=3 distinct pitch classes
        # but <=2 notes sounding together). Detected per-bar, so block chords elsewhere don't mask it.
        sim_at, pcs_in = {}, {}
        for e in events:
            k = (e["bar"], round(e["onb"], 3)); sim_at[k] = sim_at.get(k, 0) + 1
            pcs_in.setdefault(e["bar"], set()).add(e["midi"] % 12)
        bar_maxsim = {}
        for (bar, _on), c in sim_at.items():
            bar_maxsim[bar] = max(bar_maxsim.get(bar, 0), c)
        ok = any(len(pcs_in[b]) >= 3 and bar_maxsim.get(b, 0) <= 2 for b in pcs_in)
        return ("broken/arpeggiated figuration present (a bar outlines a chord ≤2-at-once)", ok, None)
    if cid in ("TX-BLOCK-CHORDS", "TX-HOMOPHONIC"):
        sim = _max_simultaneity(events); return (f"block-chord texture (max simultaneity {sim}≥3)", sim >= 3, sim)
    # default: not auto-verifiable -> report as manual (does not fail the gate)
    return (f"{cid} present (manual review — no auto-detector)", None, None)


def _header(text):
    h = text.splitlines()[0] if text.strip() else ""
    meter = (re.search(r"METER:\s*(\S+)", h) or [None, None])[1]
    tempo = (re.search(r"TEMPO:\s*(\d+)", h) or [None, None])[1]
    return meter, (int(tempo) if tempo else None)


def _chord_labels(text):
    """All chord tokens across bars (split `[A | B]`, drop `-`)."""
    out = []
    for m in re.finditer(r"^@\d+\s*\[([^\]]*)\]", text, re.M):
        for tok in m.group(1).split("|"):
            tok = tok.strip()
            if tok and tok != "-":
                out.append(tok)
    return out


def check_requirements(case, events, text):
    """Verify the user's explicit requirements (meter / tempo / chords / rhythm-feel). Returns list of
    (label, passed-or-None, detail); None = informational (not gated)."""
    meter, tempo = _header(text); reqs = []; bu = _beat_unit(meter)
    if case.get("meter"):
        reqs.append((f"time signature {meter} == {case['meter']}", meter == case["meter"], meter))
    if case.get("tempo_range"):
        lo, hi = case["tempo_range"]; ok = tempo is not None and lo <= tempo <= hi
        reqs.append((f"tempo {tempo} in [{lo},{hi}] (~{case.get('tempo_bpm')})", ok, tempo))
    labels = _chord_labels(text); freq = Counter(labels)
    if case.get("require_chords"):
        miss = [c for c in case["require_chords"] if c not in freq]
        reqs.append((f"required chords present {case['require_chords']}" + (f" — MISSING {miss}" if miss else ""),
                     not miss, dict(freq)))
    if case.get("dominant_chord"):
        top = freq.most_common(1)[0][0] if freq else None
        reqs.append((f"most-used chord == {case['dominant_chord']} (got {top})",
                     top == case["dominant_chord"], dict(freq)))
    if case.get("syncopation_band"):
        lo, hi = case["syncopation_band"]; ratio = round(_offbeat_ratio(events, bu), 2)
        reqs.append((f"syncopation amount '{case.get('syncopation')}' off-beat ratio {ratio} in [{lo:.2f},{hi:.2f}]",
                     lo <= ratio <= hi, ratio))
    ft = case.get("rhythm_feel_target")
    if ft:
        durs = [e["dur"] for e in events]; med = round(statistics.median(durs), 2) if durs else 0
        nbars = max(1, len({e["bar"] for e in events})); opb = round(len(events) / nbars, 2)
        ok = True
        if "max_median_dur" in ft and med > ft["max_median_dur"]: ok = False
        if "min_median_dur" in ft and med < ft["min_median_dur"]: ok = False
        if "min_onsets_per_bar" in ft and opb < ft["min_onsets_per_bar"]: ok = False
        if "max_onsets_per_bar" in ft and opb > ft["max_onsets_per_bar"]: ok = False
        reqs.append((f"rhythm feel '{ft['feel']}' (median dur {med}, {opb} onsets/bar)", ok, dict(median=med, opb=opb)))
    if case.get("range_min"):
        mids = [e["midi"] for e in events]
        span = (max(mids) - min(mids)) if mids else 0
        reqs.append((f"melodic range span {span} ≥ {case['range_min']} semitones", span >= case["range_min"], span))
    if case.get("melody_interest"):
        iv = _melodic_intervals(events); sg = _signed_intervals(events)
        distinct = len({e["midi"] for e in events})
        step_frac = (sum(1 for i in iv if i <= 2) / len(iv)) if iv else 0.0
        has_leap = any(i >= 3 for i in iv)
        both_dir = any(s > 0 for s in sg) and any(s < 0 for s in sg)
        # A broken-chord/arpeggio/Alberti figuration study is leap-based by nature — don't demand stepwise
        # motion there; the interest is the figuration. Otherwise keep a lenient stepwise floor.
        figuration = any(c in (case.get("concept_ids") or [])
                         for c in ("TX-ARPEGGIO", "TX-BROKEN-CHORDS", "TX-ALBERTI-BASS"))
        step_min = 0.0 if figuration else 0.25
        ok = step_frac >= step_min and has_leap and both_dir and distinct >= 5
        reqs.append((f"melodic interest (step {step_frac:.2f}≥{step_min}{' [figuration]' if figuration else ''}, "
                     f"has-leap {has_leap}, up&down {both_dir}, {distinct} distinct≥5)", ok,
                     dict(step=round(step_frac, 2), leap=has_leap, both_dir=both_dir, distinct=distinct)))
    if case.get("grand_staff_band"):
        gs = case["grand_staff_band"]
        mids = [e["midi"] for e in events]
        used = set(mids)
        lo, hi = (min(mids), max(mids)) if mids else (60, 60)
        n = max(1, len(mids))
        bass_frac = sum(1 for m in mids if m < 60) / n      # below middle C -> bass clef
        treble_frac = sum(1 for m in mids if m >= 60) / n   # middle C and up -> treble clef
        # COVERAGE: of the in-key pitches a reader meets across [cover_lo, cover_hi], how many actually appear?
        _, pcs, _ = scale_pcs(case.get("key", "C major"))
        target = [m for m in range(gs["cover_lo"], gs["cover_hi"] + 1) if m % 12 in pcs]
        cover_frac = (sum(1 for m in target if m in used) / len(target)) if target else 0.0
        ok = (lo <= gs["low_max"] and hi >= gs["high_min"]
              and bass_frac >= gs["min_low_frac"] and treble_frac >= gs["min_high_frac"]
              and cover_frac >= gs["cover_min"])
        reqs.append((f"grand-staff span+coverage: lowest {lo}≤{gs['low_max']} & highest {hi}≥{gs['high_min']}, "
                     f"bass/treble share {bass_frac:.2f}/{treble_frac:.2f} ≥{gs['min_low_frac']:.2f}, "
                     f"covers {cover_frac:.2f}≥{gs['cover_min']:.2f} of in-key staff pitches "
                     f"(both clefs, hits most notes a reader meets)", ok,
                     dict(low=lo, high=hi, bass_frac=round(bass_frac, 2), treble_frac=round(treble_frac, 2),
                          coverage=round(cover_frac, 2))))
    if case.get("clef_band"):
        cb = case["clef_band"]
        mids = [e["midi"] for e in events]
        lo, hi = (min(mids), max(mids)) if mids else (60, 60)
        _, pcs, _ = scale_pcs(case.get("key", "C major"))
        target = [m for m in range(cb["cover_lo"], cb["cover_hi"] + 1) if m % 12 in pcs]
        cover = (sum(1 for m in target if m in set(mids)) / len(target)) if target else 0.0
        if cb["mode"] == "treble":
            ok = hi >= cb["hi_min"] and lo >= cb["lo_floor"] and cover >= cb["cover_min"]
            lbl = (f"treble-clef register: highest {hi}≥{cb['hi_min']} and lowest {lo}≥{cb['lo_floor']} "
                   f"(stay in/above the treble staff), covers {cover:.2f}≥{cb['cover_min']:.2f} of treble-clef pitches")
        else:
            ok = lo <= cb["lo_max"] and hi <= cb["hi_ceil"] and cover >= cb["cover_min"]
            lbl = (f"bass-clef register: lowest {lo}≤{cb['lo_max']} and highest {hi}≤{cb['hi_ceil']} "
                   f"(stay in/below the bass staff), covers {cover:.2f}≥{cb['cover_min']:.2f} of bass-clef pitches")
        reqs.append((lbl, ok, dict(low=lo, high=hi, coverage=round(cover, 2))))
    if case.get("single_line"):
        # monophonic: essentially one note at a time (arpeggiate harmony), so it engraves on ONE staff with
        # clef changes rather than a grand staff. Allow a rare dyad but never a block chord.
        cnt = Counter((e["bar"], round(e["onb"], 3)) for e in events)
        counts = list(cnt.values())
        max_sim = max(counts) if counts else 0
        poly_frac = (sum(1 for c in counts if c >= 2) / len(counts)) if counts else 0.0
        ok = max_sim <= 2 and poly_frac <= 0.10
        reqs.append((f"single line (monophonic): max simultaneity {max_sim}≤2, {poly_frac:.2f}≤0.10 of onsets "
                     f"have ≥2 notes (arpeggiate harmony; no block chords) — engraves on ONE clef-changing staff",
                     ok, dict(max_sim=max_sim, poly_frac=round(poly_frac, 2))))
    if case.get("rhythm_mix"):
        # per-bar rhythm signature = the sorted (onset, duration) pattern of that bar (pitch-independent).
        # Require: several distinct patterns, none run in a block (longest identical run ≤ 2), and the rhythm
        # changes bar-to-bar often (interleaved, no obvious separation).
        by_bar = {}
        for e in events:
            by_bar.setdefault(e["bar"], []).append((round(e["onb"], 3), round(e["dur"], 3)))
        sigs = [tuple(sorted(by_bar[b])) for b in sorted(by_bar)]
        nb = len(sigs)
        distinct = len(set(sigs))
        max_run, cur = (1, 1) if nb else (0, 0)
        for i in range(1, nb):
            cur = cur + 1 if sigs[i] == sigs[i - 1] else 1
            max_run = max(max_run, cur)
        change_frac = (sum(1 for i in range(1, nb) if sigs[i] != sigs[i - 1]) / (nb - 1)) if nb > 1 else 0.0
        ok = distinct >= min(3, nb) and max_run <= 2 and change_frac >= 0.5
        reqs.append((f"rhythm mixed & non-repetitive: {distinct} distinct bar-rhythms, longest identical run "
                     f"{max_run}≤2, adjacent-change {change_frac:.2f}≥0.50 (patterns interleaved, no block "
                     f"separation)", ok, dict(distinct=distinct, max_run=max_run, change_frac=round(change_frac, 2))))
    if case.get("dynamics"):
        reqs.append((f"dynamics requested: {case['dynamics']} (performance overlay — not gated)", None, None))
    return reqs


def novelty(path, shown_grammars):
    """Copy-control: copy_risk vs corpus + max overlap vs each shown grammar (kb example / exemplar)."""
    cr = copy_risk(str(path), vs_corpus=True)["copy_risk"]
    gen_bb, _, gen_tot = piece_notes(path)
    shown_max = 0.0
    tmp = Path(tempfile.mkdtemp())
    for i, g in enumerate(shown_grammars or []):
        p = tmp / f"s{i}.txt"; p.write_text(g.strip() + "\n")
        try:
            sb, _, _ = piece_notes(p)
            ov, _ = slide_overlap(gen_bb, gen_tot, sb)
            shown_max = max(shown_max, ov)
        except Exception:
            pass
    return cr, round(shown_max, 3)


def measure(path, case):
    path = Path(path)
    s = Song(path); events = s.events; grammar_text = path.read_text()
    voices = sorted({e["voice"] for e in events})
    single = len(voices) == 1
    bars = len({e["bar"] for e in events})

    tonic_pc, pcs, mode = scale_pcs(case["key"])
    out_notes = sum(1 for e in events if e["midi"] % 12 not in pcs)
    out_frac = out_notes / max(1, len(events))
    in_key = out_frac <= CHROMATIC_ALLOWANCE

    bu = _beat_unit(case.get("meter") or _header(grammar_text)[0])
    checks = [detect_challenge(c, events, grammar_text, bu) for c in case["concept_ids"]]
    auto = [(lbl, ok) for lbl, ok, _ in checks if ok is not None]
    challenge_pass = all(ok for _, ok in auto) if auto else True

    reqs = check_requirements(case, events, grammar_text)
    req_pass = all(ok for _, ok, _ in reqs if ok is not None)

    cr, shown_max = novelty(path, case.get("shown_grammars"))
    novel = cr < CORPUS_THR and shown_max < SHOWN_THR

    verdict = single and in_key and challenge_pass and req_pass and novel and bars >= 2
    return dict(
        path=path.name, bars=bars, voices=voices, single_channel=single,
        key=case["key"], scale_mode=mode, out_of_scale_frac=round(out_frac, 3), in_key=in_key,
        challenge_checks=[{"check": lbl, "pass": ok, "detail": d} for lbl, ok, d in checks],
        challenge_pass=challenge_pass,
        requirement_checks=[{"check": lbl, "pass": ok, "detail": d} for lbl, ok, d in reqs],
        requirement_pass=req_pass,
        copy_vs_corpus=cr, copy_vs_corpus_thr=CORPUS_THR,
        copy_vs_shown=shown_max, copy_vs_shown_thr=SHOWN_THR, novel=novel,
        verdict=bool(verdict),
    )
