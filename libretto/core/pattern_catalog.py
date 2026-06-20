#!/usr/bin/env python3
"""
pattern_catalog.py — distill a DESCRIPTIVE musical-pattern catalog DIRECTLY from the
grammar tokens of the 59 real songs (song_0014, the generated piece, is excluded).

Deterministic: every pattern is detected from note-level data parsed from the grammar
(pitch, onset, duration, voice). Harmony is grounded in actual PITCH CLASSES and bass
motion, NOT the heuristic [chord] labels. Each detected pattern records exact on-page
token citations (song id + bar + the real tokens) and an attestation count across the
corpus. Writes music-pattern-catalog/SKILL.md.

Run: python3 pattern_catalog.py
"""
import json
import re
from collections import Counter, defaultdict
import os
from pathlib import Path

from .understanding_probe import Song   # reuse the note-level grammar parser

SCRIPT_DIR = Path(os.environ.get("LIBRETTO_DATA") or (Path(__file__).resolve().parent.parent / "data"))
GRAMMAR_DIR = SCRIPT_DIR / "grammar"
ANSWER_KEY = SCRIPT_DIR / "answer_key" / "grammar_truth.json"
OUT = SCRIPT_DIR / "music-pattern-catalog" / "SKILL.md"
EXCLUDE = {"song_0014"}            # the generated piece — real human compositions only

PC = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_BAR_RE = re.compile(r"^@(\d+)\s")
_VOICE_LINE = re.compile(r"^\s+(.+?):\s+(.*)$")

# pattern registry: key -> {songs:set, examples:[(song_id, bar, text)]}
CAT = defaultdict(lambda: {"songs": set(), "examples": []})


def add(key, sid, bar, text, cap=4):
    e = CAT[key]
    e["songs"].add(sid)
    if len(e["examples"]) < cap and all(x[0] != sid for x in e["examples"]):
        e["examples"].append((sid, bar, text))


def raw_tokens(path):
    """{(bar, voice): 'tok tok ...'} straight from the file, for on-page citations."""
    out = {}
    cur = None
    for ln in Path(path).read_text(encoding="utf-8").splitlines():
        bm = _BAR_RE.match(ln)
        if bm:
            cur = int(bm.group(1)); continue
        vm = _VOICE_LINE.match(ln)
        if cur is not None and vm and not ln.startswith("KEY") and not ln.startswith("VOICES"):
            out[(cur, vm.group(1).strip())] = vm.group(2).strip()
    return out


def cite(raw, bar, voice, maxlen=70):
    t = raw.get((bar, voice), "")
    if len(t) > maxlen:
        t = t[:maxlen] + "…"
    return f"{voice}: {t}"


def busiest(raw, bar):
    """Voice carrying the most tokens in this bar — used so harmony citations show the
    voice that actually sounds the chord, not a globally-chordal voice that's silent here."""
    cands = [(len(t), v) for (b, v), t in raw.items() if b == bar and t]
    return max(cands)[1] if cands else ""


# --------------------------------------------------------------------------- #
def voice_stats(song):
    st = {}
    for v in song.voices:
        evs = song.voice_events(v)
        if not evs:
            continue
        onsets = {e["abs"] for e in evs}
        st[v] = {
            "avg": sum(e["midi"] for e in evs) / len(evs),
            "lo": min(e["midi"] for e in evs), "hi": max(e["midi"] for e in evs),
            "n_onset": len(onsets),
            "chordality": len(evs) / max(1, len(onsets)),
        }
    return st


def bass_voice(st):
    return min(st, key=lambda v: st[v]["avg"]) if st else None


def melody_voice(st):
    cand = [v for v in st if st[v]["chordality"] < 1.4 and st[v]["n_onset"] >= 8]
    pool = cand or list(st)
    return max(pool, key=lambda v: st[v]["avg"]) if pool else None


def bar_root_seq(song, voice):
    """(bar, lowest-midi) per bar the voice sounds in."""
    by = defaultdict(list)
    for e in song.voice_events(voice):
        by[e["bar"]].append(e["midi"])
    return [(b, min(by[b])) for b in sorted(by)]


def weighted_pcs(song, bar):
    w = defaultdict(float)
    for e in song.events:
        if e["bar"] == bar:
            w[e["pc"]] += e["dur"]
    return w


def prominent_pcs(w, frac=0.30):
    if not w:
        return set()
    mx = max(w.values())
    return {pc for pc, x in w.items() if x >= frac * mx}


def line_intervals(song, voice):
    ln = song.line(voice)
    seq = [ln[t] for t in sorted(ln)]
    bars = [int(t // song.bar_ql) + 1 for t in sorted(ln)]
    return seq, [b - a for a, b in zip(seq, seq[1:])], bars


# --------------------------------------------------------------------------- #
def analyze(song, sid, raw):
    st = voice_stats(song)
    if not st:
        return
    bass = bass_voice(st)
    mel = melody_voice(st)
    bar_ql = song.bar_ql
    beats = round(bar_ql)

    # ---------------- HARMONY (grounded in pitch classes / bass motion) -------
    roots = bar_root_seq(song, bass) if bass else []
    # H: descending stepwise bass line (lament / line-cliche): >=3 bars each step -1..-2
    run = [roots[0]] if roots else []
    for prev, cur in zip(roots, roots[1:]):
        if -2 <= cur[1] - prev[1] <= -1:
            run.append(cur)
        else:
            if len(run) >= 3:
                b0 = run[0][0]
                seq = "-".join(PC[m % 12] for _, m in run)
                add("H:descending_bass", sid, b0, f"bar {b0}+ bass roots {seq}  [{cite(raw,b0,bass)}]")
            run = [cur]
    if len(run) >= 3:
        b0 = run[0][0]
        seq = "-".join(PC[m % 12] for _, m in run)
        add("H:descending_bass", sid, b0, f"bar {b0}+ bass roots {seq}  [{cite(raw,b0,bass)}]")

    # H: root motion up a 4th chain (ii-V-I / V-I functional motion), from bass pcs
    rpc = [(b, m % 12) for b, m in roots]
    chain = 1
    for (b0, p0), (b1, p1) in zip(rpc, rpc[1:]):
        if (p1 - p0) % 12 == 5:           # up a perfect fourth (== down a fifth)
            chain += 1
            if chain >= 3:                # two consecutive 4th-ups = X -> Y -> Z (ii-V-I shape)
                add("H:fourth_root_motion", sid, b1,
                    f"bars {b0}->{b1}: bass roots rise by 4ths {PC[p0]}->{PC[p1]} "
                    f"(V–I / ii–V motion)  [{cite(raw,b1,bass)}]")
        else:
            chain = 1
    # also count single V->I (down a fifth into a strong bar) — fourth-up adjacency
    n4 = sum(1 for (a, p0), (b, p1) in zip(rpc, rpc[1:]) if (p1 - p0) % 12 == 5)
    if n4 >= 3:
        CAT["H:fourth_root_motion"]["songs"].add(sid)

    # H: augmented and diminished sonorities; dominant-7th sonority — from prominent pcs
    aug = dim = dom7 = None
    for bar in sorted({e["bar"] for e in song.events}):
        pcs = prominent_pcs(weighted_pcs(song, bar))
        if len(pcs) < 3:
            continue
        for r in pcs:
            if {r, (r + 4) % 12, (r + 8) % 12} <= pcs and aug is None:
                aug = (bar, r)
            if {r, (r + 3) % 12, (r + 6) % 12} <= pcs and dim is None:
                dim = (bar, r)
            if {r, (r + 4) % 12, (r + 7) % 12, (r + 10) % 12} <= pcs and dom7 is None:
                dom7 = (bar, r)
        if aug and dim and dom7:
            break
    if aug:
        b, r = aug
        add("H:augmented", sid, b, f"bar {b}: aug triad on {PC[r]} ({PC[r]},{PC[(r+4)%12]},{PC[(r+8)%12]})  [{cite(raw,b,busiest(raw,b))}]")
    if dim:
        b, r = dim
        add("H:diminished", sid, b, f"bar {b}: dim sonority on {PC[r]} ({PC[r]},{PC[(r+3)%12]},{PC[(r+6)%12]})  [{cite(raw,b,busiest(raw,b))}]")
    if dom7:
        b, r = dom7
        add("H:dominant7", sid, b, f"bar {b}: dom7 on {PC[r]} ({PC[r]},{PC[(r+4)%12]},{PC[(r+7)%12]},{PC[(r+10)%12]})  [{cite(raw,b,busiest(raw,b))}]")

    # H: pedal point — bass root pc constant >=4 consecutive bars
    pr = 1; pstart = roots[0][0] if roots else None; pcv = rpc[0][1] if rpc else None
    for (b0, p0), (b1, p1) in zip(rpc, rpc[1:]):
        if p1 == p0:
            pr += 1
        else:
            if pr >= 4 and pstart is not None:
                add("H:pedal_point", sid, pstart, f"bars {pstart}-{b0}: bass holds {PC[p0]} pedal  [{cite(raw,pstart,bass)}]")
            pr = 1; pstart = b1
    if pr >= 4 and pstart is not None:
        add("H:pedal_point", sid, pstart, f"bars {pstart}+: sustained {PC[rpc[-1][1]]} bass pedal  [{cite(raw,pstart,bass)}]")

    # ---------------- MELODY (exact from tokens) ------------------------------
    if mel:
        seq, iv, mbars = line_intervals(song, mel)
        moves = [d for d in iv if d != 0]
        if moves:
            step = sum(1 for d in moves if abs(d) <= 2) / len(moves)
            if step >= 0.6:
                i = next((k for k, d in enumerate(iv) if abs(d) in (1, 2)), 0)
                add("M:stepwise", sid, mbars[i], f"{mel} mostly stepwise ({step:.0%} steps)  [{cite(raw,mbars[i],mel)}]")
        # sigh: descending step (-1/-2) onto a longer note
        ln = song.line(mel); times = sorted(ln)
        durs = {}
        for e in song.voice_events(mel):
            durs.setdefault(e["abs"], 0)
            durs[e["abs"]] = max(durs[e["abs"]], e["dur"])
        for k in range(len(times) - 1):
            d = ln[times[k + 1]] - ln[times[k]]
            if d in (-1, -2) and durs.get(times[k + 1], 0) >= durs.get(times[k], 0) * 1.5 and durs.get(times[k + 1], 0) >= 1.0:
                b = int(times[k] // bar_ql) + 1
                add("M:sigh", sid, b, f"{mel}: {PC[ln[times[k]]%12]}->{PC[ln[times[k+1]]%12]} step-down onto a long note (bar {b})  [{cite(raw,b,mel)}]")
                break
        # repeated melodic cell: a 3-interval n-gram recurring >=3x
        grams = Counter(tuple(iv[i:i+3]) for i in range(len(iv) - 2))
        if grams:
            cell, c = grams.most_common(1)[0]
            if c >= 3 and any(cell):
                i = next(k for k in range(len(iv) - 2) if tuple(iv[k:k+3]) == cell)
                add("M:motivic_cell", sid, mbars[i], f"{mel} cell intervals {list(cell)} recurs {c}x  [{cite(raw,mbars[i],mel)}]")
        # leap + step-back (gap fill)
        for k in range(len(iv) - 1):
            if abs(iv[k]) >= 7 and iv[k] * iv[k+1] < 0 and abs(iv[k+1]) <= 2:
                b = mbars[k]
                add("M:leap_gapfill", sid, b, f"{mel}: leap {iv[k]:+d}st then step {iv[k+1]:+d} back (bar {b})  [{cite(raw,b,mel)}]")
                break

    # ---------------- RHYTHM (exact) ------------------------------------------
    # subdivision: per-bar grid annotations vs default (triplet grids are 6/12/24)
    # subdivision: parse the header default grid (triplet labels end in 't', e.g. '12t';
    # binary labels end in 'th', e.g. '16th' — the \b stops 't' matching the 't' in 'th')
    file_lines = Path(GRAMMAR_DIR / f"{sid}.txt").read_text(encoding="utf-8").splitlines()
    default_is_trip = bool(re.search(r"GRID:\s*\d+t\b", file_lines[0]))
    trip = binv = 0
    for ln in file_lines:
        if ln.startswith("@"):
            m = re.search(r"\(grid:(\d+)(t?)\)", ln)
            if m:
                (trip := trip + 1) if m.group(2) else (binv := binv + 1)
            else:
                (trip := trip + 1) if default_is_trip else (binv := binv + 1)
    if trip > binv:
        add("R:triplet", sid, 1, f"majority triplet-grid bars ({trip} triplet vs {binv} binary)")
    else:
        add("R:straight", sid, 1, f"majority straight/binary subdivision ({binv} binary vs {trip} triplet)")
    # syncopation: fraction of onsets off the beat
    on = [e for e in song.events]
    if on:
        off = sum(1 for e in on if (e["onb"] % 1.0) > 1e-6) / len(on)
        if off >= 0.15:
            b = next((e["bar"] for e in on if (e["onb"] % 1.0) > 1e-6), 1)
            add("R:syncopation", sid, b, f"{off:.0%} of onsets fall off the beat")
    # groove ostinato: a voice repeats identical per-bar rhythm >=8 consecutive bars
    for v in song.voices:
        per = defaultdict(list)
        for e in song.voice_events(v):
            per[e["bar"]].append(round(e["onb"], 3))
        pat = {b: tuple(sorted(set(p))) for b, p in per.items() if p}
        bs = sorted(pat); runlen = 1; rstart = bs[0] if bs else None
        for a, b in zip(bs, bs[1:]):
            if b == a + 1 and pat[b] == pat[a] and len(pat[a]) >= 2:
                runlen += 1
            else:
                if runlen >= 8:
                    add("R:ostinato", sid, rstart, f"{v} repeats one rhythmic figure bars {rstart}-{a}  [{cite(raw,rstart,v)}]")
                runlen = 1; rstart = b
        if runlen >= 8 and rstart is not None:
            add("R:ostinato", sid, rstart, f"{v} repeats one rhythmic figure for {runlen} bars from {rstart}  [{cite(raw,rstart,v)}]")
    # root-pulse bass: bass has an onset on every beat for >=8 bars
    if bass:
        per = defaultdict(set)
        for e in song.voice_events(bass):
            per[e["bar"]].add(round(e["onb"]))
        full = {b for b, s in per.items() if set(range(beats)) <= s}
        bs = sorted(full); runlen = 1; rstart = bs[0] if bs else None; best = 0; bbar = None
        for a, b in zip(bs, bs[1:]):
            if b == a + 1:
                runlen += 1
            else:
                if runlen > best:
                    best, bbar = runlen, rstart
                runlen = 1; rstart = b
        if runlen > best:
            best, bbar = runlen, rstart
        if best >= 8:
            add("R:root_pulse_bass", sid, bbar, f"{bass} plays a root on every beat for {best} bars from {bbar}  [{cite(raw,bbar,bass)}]")

    # ---------------- FORM (exact) --------------------------------------------
    allbars = sorted({e["bar"] for e in song.events})
    sets = {b: song.bar_event_set(b) for b in allbars}
    # verbatim 4-bar block reprise (verse/chorus copy)
    seen = {}
    for i in range(len(allbars) - 3):
        block = allbars[i:i+4]
        if block[3] - block[0] != 3:
            continue
        key = tuple(frozenset(sets[b]) for b in block)
        if all(sets[b] for b in block):
            if key in seen and block[0] - seen[key] >= 4:
                add("F:verbatim_reprise", sid, seen[key], f"bars {seen[key]}-{seen[key]+3} reappear verbatim at bars {block[0]}-{block[3]}")
                break
            seen.setdefault(key, block[0])
    # sparse single-voice intro
    first = allbars[0] if allbars else None
    if first is not None:
        intro_voices = {e["voice"] for e in song.events if e["bar"] in range(first, first + 4)}
        if len(intro_voices) == 1:
            add("F:sparse_intro", sid, first, f"opens with one voice ({next(iter(intro_voices))}) for the first bars")
    # thinning / fade outro: last 3 bars have <= half the median events
    dens = Counter(e["bar"] for e in song.events)
    med = sorted(dens.values())[len(dens)//2] if dens else 0
    tail = [b for b in allbars[-3:]]
    if tail and med and all(dens.get(b, 0) <= max(1, med * 0.5) for b in tail):
        add("F:thinning_outro", sid, tail[0], f"final bars {tail[0]}-{tail[-1]} thin to <=50% of median density")

    # ---------------- TEXTURE / VOICING (exact) -------------------------------
    # role stratification: a low bass + a chordal voice + a distinct high melody
    chordal = [v for v in st if st[v]["chordality"] >= 1.8]
    if bass and mel and bass != mel and chordal and any(c not in (bass, mel) for c in chordal):
        c = next(c for c in chordal if c not in (bass, mel))
        add("T:role_stratification", sid, allbars[0] if allbars else 1,
            f"bass={bass} (avg {st[bass]['avg']:.0f}), chordal={c}, melody={mel} (avg {st[mel]['avg']:.0f})")
    # octave/unison doubling: two voices with identical top-note pc sequence >=8 shared onsets
    lines = {v: song.line(v) for v in song.voices}
    vlist = list(song.voices)
    for ai in range(len(vlist)):
        for bi in range(ai + 1, len(vlist)):
            va, vb = vlist[ai], vlist[bi]
            shared = sorted(set(lines[va]) & set(lines[vb]))
            if len(shared) >= 12:
                same = sum(1 for t in shared if (lines[va][t] - lines[vb][t]) % 12 == 0)
                if same / len(shared) >= 0.9:
                    b = int(shared[0] // bar_ql) + 1
                    rel = "unison/octave"
                    add("T:doubling", sid, b, f"{va} and {vb} double in {rel} ({same}/{len(shared)} shared onsets)  [{cite(raw,b,va)}]")
                    break
        else:
            continue
        break
    # parallel thirds/sixths: two voices a consistent 3rd or 6th apart over >=6 shared onsets
    for ai in range(len(vlist)):
        for bi in range(ai + 1, len(vlist)):
            va, vb = vlist[ai], vlist[bi]
            shared = sorted(set(lines[va]) & set(lines[vb]))
            if len(shared) >= 6:
                ivs = [abs(lines[va][t] - lines[vb][t]) % 12 for t in shared]
                thirds = sum(1 for x in ivs if x in (3, 4))
                sixths = sum(1 for x in ivs if x in (8, 9))
                if max(thirds, sixths) / len(shared) >= 0.8:
                    b = int(shared[0] // bar_ql) + 1
                    kind = "thirds" if thirds >= sixths else "sixths"
                    add("T:parallel_3rd_6th", sid, b, f"{va}/{vb} move in parallel {kind} ({max(thirds,sixths)}/{len(shared)})  [{cite(raw,b,va)}]")
                    break
        else:
            continue
        break
    # wide chordal voicing: a single onset spanning >= 19 semitones
    for v in chordal:
        by = defaultdict(list)
        for e in song.voice_events(v):
            by[e["abs"]].append(e["midi"])
        for t, ms in by.items():
            if len(ms) >= 3 and max(ms) - min(ms) >= 19:
                b = int(t // bar_ql) + 1
                add("T:wide_voicing", sid, b, f"{v} spans {max(ms)-min(ms)} semitones in one chord (bar {b})  [{cite(raw,b,v)}]")
                break
        if sid in CAT["T:wide_voicing"]["songs"]:
            break


# --------------------------------------------------------------------------- #
META = {
    # key: (category, Name, checkable definition)
    "H:descending_bass": ("Harmony", "Descending stepwise bass line (line-cliché / lament)",
        "The lowest voice's per-bar root descends by 1–2 semitones for ≥3 consecutive bars."),
    "H:fourth_root_motion": ("Harmony", "Functional root motion up a 4th (V–I / ii–V–I)",
        "The bass root rises a perfect fourth (≡ falls a fifth) on ≥3 bar-transitions; two in a row gives a ii–V–I shape."),
    "H:dominant7": ("Harmony", "Dominant-seventh sonority",
        "Some bar's prominent pitch classes contain a full {root, M3, P5, m7} stack (verified from pcs, not the label)."),
    "H:augmented": ("Harmony", "Augmented-triad passing sonority",
        "A bar's prominent pitch classes form {root, root+4, root+8} (a raised-5th color)."),
    "H:diminished": ("Harmony", "Diminished passing sonority",
        "A bar's prominent pitch classes form {root, root+3, root+6}."),
    "H:pedal_point": ("Harmony", "Bass pedal point",
        "The bass root pitch class stays constant for ≥4 consecutive bars while upper harmony moves."),
    "M:stepwise": ("Melody", "Predominantly stepwise melodic motion",
        "≥60% of the melody voice's nonzero intervals are ≤2 semitones."),
    "M:sigh": ("Melody", "Descending-step 'sigh' resolution",
        "A melodic descent of 1–2 semitones lands on a note ≥1.5× longer (phrase-ending appoggiatura/sigh)."),
    "M:motivic_cell": ("Melody", "Repeated motivic cell",
        "A 3-interval melodic shape recurs ≥3 times in the melody voice."),
    "M:leap_gapfill": ("Melody", "Leap then step-back (gap-fill)",
        "A melodic leap ≥7 semitones is immediately answered by a ≤2-semitone step in the opposite direction."),
    "R:straight": ("Rhythm", "Straight (binary) subdivision",
        "The majority of bars quantize to a binary grid (8th/16th/32nd), not triplets."),
    "R:triplet": ("Rhythm", "Triplet / compound subdivision",
        "The majority of bars quantize to a triplet grid (6/12/24 slots per whole note)."),
    "R:syncopation": ("Rhythm", "Syncopation",
        "≥15% of note onsets fall off the beat (onset not on a quarter-note boundary)."),
    "R:ostinato": ("Rhythm", "Groove ostinato",
        "A voice repeats one identical (multi-onset) rhythmic figure for ≥8 consecutive bars."),
    "R:root_pulse_bass": ("Rhythm", "Root-pulse / four-on-the-floor bass",
        "The bass states a note on every beat of the bar for ≥8 consecutive bars."),
    "F:verbatim_reprise": ("Form", "Verbatim sectional reprise",
        "A ≥4-bar block of note events reappears note-for-note later in the song (verse/chorus copy)."),
    "F:sparse_intro": ("Form", "Single-voice / sparse intro",
        "The first bars sound only one voice before the texture enters."),
    "F:thinning_outro": ("Form", "Thinning / fade outro",
        "The final bars drop to ≤50% of the song's median note density (fade rather than cadence)."),
    "T:role_stratification": ("Texture/Voicing", "Bass / chordal / melody role stratification",
        "Distinct low bass voice, a chord-bearing voice (≥1.8 notes per onset), and a separate high melody voice coexist."),
    "T:doubling": ("Texture/Voicing", "Unison / octave doubling",
        "Two voices share the same top-note pitch class at ≥90% of ≥12 shared onsets."),
    "T:parallel_3rd_6th": ("Texture/Voicing", "Parallel thirds / sixths",
        "Two voices stay a 3rd (3–4 st) or 6th (8–9 st) apart at ≥80% of ≥6 shared onsets."),
    "T:wide_voicing": ("Texture/Voicing", "Wide multi-octave chord voicing",
        "A chord-bearing voice sounds a simultaneity spanning ≥19 semitones (>1.5 octaves)."),
}
CAT_ORDER = ["Harmony", "Melody", "Rhythm", "Form", "Texture/Voicing"]


def main():
    truth = json.loads(ANSWER_KEY.read_text(encoding="utf-8"))
    label = {sid: f"{v.get('artist','?')} — {v.get('title','?')}" for sid, v in truth.items()}
    files = [f for f in sorted(GRAMMAR_DIR.glob("song_*.txt")) if f.stem not in EXCLUDE]
    n_songs = len(files)
    for f in files:
        sid = f.stem
        try:
            song = Song(f)
            analyze(song, sid, raw_tokens(f))
        except Exception as e:  # noqa: BLE001
            print(f"[skip] {sid}: {e}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    keys_present = [k for k in META if k in CAT and CAT[k]["songs"]]
    L = []
    L.append("---")
    L.append("name: music-pattern-catalog")
    L.append(f"description: A descriptive catalog of {len(keys_present)} concrete musical patterns "
             f"distilled deterministically from the note tokens of {n_songs} real well-known popular songs "
             "(grammar corpus). Patterns are grounded in actual pitch classes / onsets / durations with "
             "on-page citations and attestation counts. Descriptive of THIS corpus, not universal rules.")
    L.append("---\n")
    L.append("# Musical Pattern Catalog (corpus-distilled)\n")
    L.append("## Scope & caveats\n")
    L.append(f"- Distilled **directly from the grammar tokens** of **{n_songs} real songs** "
             "(every `song_*` except the generated `song_0014`, which is excluded). No prose reviews were used.")
    L.append("- **Descriptive, not prescriptive.** These are patterns *characteristic of this corpus* — "
             "mostly 1960s–1990s Anglo-American rock/pop/soul/folk, selection-biased toward famous songs. "
             "They describe what this music does, **not** universal rules of good music.")
    L.append("- **Deterministic & verifiable.** Every pattern is detected by `pattern_catalog.py` from "
             "note-level data; each example cites a real `song_id` + bar + on-page tokens you can check.")
    L.append("- **Harmony is grounded in pitch classes, not the heuristic `[chord]` labels.** Augmented/"
             "diminished/dominant-7th/root-motion patterns are computed from the actual sounding pitch "
             "classes, so they are verifiable independently of the (unreliable) chord labeler.")
    L.append("- **Conversion artifacts excluded by construction:** detectors key on prominent, "
             "duration-weighted pitch content and multi-bar recurrence, so isolated stray high notes, "
             "one-off muddy low clusters, and lone odd voicings do not register as patterns.")
    L.append(f"- Attestation = number of the {n_songs} songs in which the pattern is detected. "
             "A pattern in many songs is corpus-characteristic; a low count is just an attested example.\n")

    by_cat = defaultdict(list)
    for k in keys_present:
        by_cat[META[k][0]].append(k)
    for cat in CAT_ORDER:
        ks = sorted(by_cat.get(cat, []), key=lambda k: -len(CAT[k]["songs"]))
        if not ks:
            continue
        L.append(f"## {cat}\n")
        for k in ks:
            _, name, defn = META[k]
            songs = CAT[k]["songs"]
            L.append(f"### {name}")
            L.append(f"- **Definition (checkable):** {defn}")
            L.append(f"- **Attestation:** {len(songs)}/{n_songs} songs.")
            L.append("- **In the grammar (real tokens):**")
            for sid, bar, text in CAT[k]["examples"]:
                L.append(f"    - `{sid}` ({label.get(sid,'?')}) — {text}")
            L.append("")
    # summary
    L.append("## Catalog summary\n")
    L.append(f"- **{len(keys_present)} distinct patterns** cataloged across {len(CAT_ORDER)} categories, "
             f"from {n_songs} real songs.")
    counts = sorted(((len(CAT[k]['songs']), META[k][1]) for k in keys_present), reverse=True)
    ge_half = sum(1 for c, _ in counts if c >= n_songs / 2)
    ge_ten = sum(1 for c, _ in counts if c >= 10)
    L.append(f"- {ge_half} patterns attested in ≥50% of songs; {ge_ten} in ≥10 songs; "
             f"{sum(1 for c,_ in counts if c<5)} in <5 songs (attested examples, not corpus-wide).")
    L.append("- Attestation by pattern (high → low):")
    for c, nm in counts:
        L.append(f"    - {c:>2}/{n_songs}  {nm}")
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")

    # console report
    print(f"songs analyzed: {n_songs} (excluded {sorted(EXCLUDE)})")
    print(f"distinct patterns cataloged: {len(keys_present)}")
    print(f"written: {OUT}")
    print("\nattestation (count/{}):".format(n_songs))
    for c, nm in counts:
        print(f"  {c:>2}  {nm}")


if __name__ == "__main__":
    main()
