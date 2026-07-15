#!/usr/bin/env python3
"""axes_v3.py — the v3 coordinate system: 39 axes DISCOVERED by the axis_evolve loop on the FAITHFUL
enriched corpus (pretty_midi-first grammar), corrected 4-principle reward (P1 gate; P2/P3/P4 objectives;
P4 prioritized, all-4-audiobox-metrics, both signs). Replaces the prior hand-authored + 33-axis sets.
metrics_for() runs the whole registry; each axis is a deterministic function of one parsed Song.
See paper_data/axis_evolve_discovery.md and axis_evolve/.
"""
import math
import statistics
import itertools
import collections
from collections import Counter, defaultdict

import numpy as np


def axis_active_voice_count(song) -> float:
    """Number of distinct voices that actually carry notes (ensemble size / textural layering); solo or duo vs full band or orchestra."""
    vs = set()
    for e in song.events:
        vs.add(e["voice"])
    return float(len(vs))


def axis_backbeat_emphasis(song) -> float:
    """Velocity-weighted emphasis on backbeats (beats 2 & 4) vs downbeats (1 & 3); rock/pop/funk/R&B accent the backbeat, waltz/classical the downbeat."""
    events = song.events
    if not events:
        return 0.0
    beat_vel = collections.defaultdict(float)
    for e in events:
        onb = e["onb"]
        b = round(onb)
        if abs(onb - b) < 0.12:
            beat_vel[int(b)] += float(e.get("vel", 64))
    back = beat_vel.get(1, 0.0) + beat_vel.get(3, 0.0)
    front = beat_vel.get(0, 0.0) + beat_vel.get(2, 0.0)
    denom = back + front
    if denom <= 0:
        return 0.0
    return back / denom


def axis_bar_pitch_range_mean(song) -> float:
    """Mean per-bar pitch span (highest minus lowest MIDI within each bar); moment-to-moment registral reach of dense contrapuntal/orchestral writing vs the tight one-octave textures of folk & simple pop (distinct from the whole-song span by measuring local, instantaneous spread)."""
    nb = song.n_bars
    if not nb or nb <= 0:
        return 0.0
    by_bar = collections.defaultdict(list)
    for e in song.events:
        b = e["bar"]
        if 1 <= b <= nb:
            by_bar[b].append(e["midi"])
    spans = [max(ms) - min(ms) for ms in by_bar.values() if len(ms) >= 2]
    if not spans:
        return 0.0
    return float(np.mean(spans))


def axis_bass_register_gap(song) -> float:
    """Registral gap between the lowest and the median sounding pitch (bass separation); genres with a dedicated low bass line (funk, rock, jazz) vs close-position textures (string quartet, a cappella)."""
    midis = song.midis()
    if len(midis) < 2:
        return 0.0
    lo = float(min(midis))
    med = float(np.median(midis))
    return med - lo


def axis_bass_syncopation(song) -> float:
    """Fraction of the bass voice's onsets that fall off the main beat (bass-line syncopation); funk/soul/R&B bass pushes and pulls off the grid while folk/country/rock bass locks the root onto downbeats (separates funk_soul_rnb from blues_gospel and folk_country)."""
    by = collections.defaultdict(list)
    for e in song.events:
        if e["voice"] in song.drum_voices:
            continue
        by[e["voice"]].append(e)
    if not by:
        return 0.0
    bassv = min(by.keys(), key=lambda v: float(np.mean([x["midi"] for x in by[v]])))
    evs = by[bassv]
    if len(evs) < 2:
        return 0.0
    off = 0
    for e in evs:
        frac = e["onb"] - math.floor(e["onb"])
        d = min(frac, 1.0 - frac)
        if d > 0.08:
            off += 1
    return off / len(evs)


def axis_bass_walk_rate(song) -> float:
    """Mean number of distinct bass pitch classes per bar (walking-bass motion); jazz/blues walking bass moves every beat, whereas rock/folk/reggae anchor one root per bar."""
    nb = song.n_bars
    if not nb or nb <= 0:
        return 0.0
    by = collections.defaultdict(list)
    for e in song.events:
        if e["voice"] in song.drum_voices:
            continue
        by[e["voice"]].append(e)
    if not by:
        return 0.0
    bassv = min(by.keys(), key=lambda v: float(np.mean([x["midi"] for x in by[v]])))
    per = collections.defaultdict(set)
    for e in by[bassv]:
        per[e["bar"]].add(e["pc"])
    if not per:
        return 0.0
    return float(np.mean([len(s) for s in per.values()]))


def axis_blue_note_content(song) -> float:
    """Duration-weighted mass on the flat-3rd, flat-5th and flat-7th relative to the best-fit major tonic (blue-note content); blues/gospel/jazz color vs diatonic pop-rock & folk."""
    pcw = song.pc_weight()
    tot = sum(pcw.values())
    if tot <= 0:
        return 0.0
    best_root = 0
    best = -1.0
    for root in range(12):
        w = pcw.get(root, 0.0) + pcw.get((root + 4) % 12, 0.0) + pcw.get((root + 7) % 12, 0.0)
        if w > best:
            best = w
            best_root = root
    blue = (pcw.get((best_root + 3) % 12, 0.0)
            + pcw.get((best_root + 6) % 12, 0.0)
            + pcw.get((best_root + 10) % 12, 0.0))
    return blue / tot


def axis_chord_simultaneity_size(song) -> float:
    """Average number of distinct pitch classes attacked together at each onset time (vertical chord thickness); dense chordal gospel/jazz/orchestral vs single-line melodic textures."""
    groups = collections.defaultdict(set)
    for e in song.events:
        if e["voice"] in song.drum_voices:
            continue
        groups[round(e["abs"] * 4) / 4.0].add(e["pc"])
    if not groups:
        return 0.0
    sizes = [len(s) for s in groups.values()]
    return float(np.mean(sizes))


def axis_chord_type_diversity(song) -> float:
    """Number of distinct transposition-invariant chord shapes (bass-relative pitch-class sets) divided by the number of chordal instants; harmonically adventurous jazz/gospel cycle through many chord types, riff/loop genres reuse a handful (tracks production-complexity)."""
    groups = collections.defaultdict(set)
    for e in song.events:
        if e["voice"] in song.drum_voices:
            continue
        groups[round(e["abs"] * 4) / 4.0].add(e["pc"])
    types = set()
    tot = 0
    for pcs in groups.values():
        if len(pcs) < 2:
            continue
        tot += 1
        m = min(pcs)
        types.add(frozenset((p - m) % 12 for p in pcs))
    if tot == 0:
        return 0.0
    return len(types) / tot


def axis_chromaticism(song) -> float:
    """Chromaticism: duration-weighted share of pitch classes lying outside the best-fitting major/natural-minor scale; captures blue notes, altered/extended harmony."""
    pcw = song.pc_weight()
    tot = sum(pcw.values())
    if tot <= 0:
        return 0.0
    major = (0, 2, 4, 5, 7, 9, 11)
    minor = (0, 2, 3, 5, 7, 8, 10)
    best_inside = 0.0
    for templ in (major, minor):
        for root in range(12):
            scale = set((root + iv) % 12 for iv in templ)
            inside = sum(pcw.get(pc, 0.0) for pc in scale)
            if inside > best_inside:
                best_inside = inside
    return 1.0 - best_inside / tot


def axis_contour_reversal_rate(song) -> float:
    """Rate of melodic-direction reversals (up->down or down->up turns) per note in the most active voice; zig-zag angular melodies vs long directional arcs/scales."""
    v = song.most_active_voice()
    if v is None:
        return 0.0
    line = song.line(v)
    if not line:
        return 0.0
    times = sorted(line.keys())
    if len(times) < 3:
        return 0.0
    seq = [line[t] for t in times]
    signs = []
    for i in range(1, len(seq)):
        d = seq[i] - seq[i - 1]
        if d > 0:
            signs.append(1)
        elif d < 0:
            signs.append(-1)
    if len(signs) < 2:
        return 0.0
    rev = sum(1 for i in range(1, len(signs)) if signs[i] != signs[i - 1])
    return rev / (len(signs) - 1)


def axis_dissonant_interval_ratio(song) -> float:
    """Share of simultaneously-sounding pitch-class pairs that form a tense interval (minor/major 2nd or tritone); harmonically spicy jazz/gospel vs consonant folk/pop triads (tracks CE aesthetic)."""
    groups = collections.defaultdict(set)
    for e in song.events:
        if e["voice"] in song.drum_voices:
            continue
        groups[round(e["abs"] * 4) / 4.0].add(e["pc"])
    tot_pairs = 0
    tense = 0
    for pcs in groups.values():
        pl = sorted(pcs)
        n = len(pl)
        if n < 2:
            continue
        for i in range(n):
            for j in range(i + 1, n):
                ic = (pl[j] - pl[i]) % 12
                ic = min(ic, 12 - ic)
                tot_pairs += 1
                if ic in (1, 2, 6):
                    tense += 1
    if tot_pairs == 0:
        return 0.0
    return tense / tot_pairs


def axis_drum_ratio(song) -> float:
    """Fraction of note onsets played by percussion voices; beat-driven genres (funk, hip-hop, rock) vs acoustic/orchestral/solo-piano with little or no drums."""
    events = song.events
    if not events:
        return 0.0
    drums = song.drum_voices
    if not drums:
        return 0.0
    d = sum(1 for e in events if e["voice"] in drums)
    return d / len(events)


def axis_drum_timbre_entropy(song) -> float:
    """Shannon entropy of the percussion pitch (GM drum piece) distribution; elaborate latin kits (congas, timbales, clave, cowbell) vs the spare kick/snare/hat loops of hiphop/rap."""
    drums = song.drum_voices
    if not drums:
        return 0.0
    counts = collections.Counter()
    for e in song.events:
        if e["voice"] in drums:
            counts[e["midi"]] += 1
    tot = sum(counts.values())
    if tot <= 0:
        return 0.0
    h = 0.0
    for c in counts.values():
        p = c / tot
        h -= p * math.log(p)
    return h


def axis_duration_cv(song) -> float:
    """Coefficient of variation of note durations; rhythmically uniform grooves (techno, comping) vs varied phrasing (jazz solos, romantic piano)."""
    durs = [e["dur"] for e in song.events if e["dur"] > 0]
    if len(durs) < 2:
        return 0.0
    m = float(np.mean(durs))
    if m <= 0:
        return 0.0
    return float(np.std(durs)) / m


def axis_harmonic_rhythm(song) -> float:
    """Harmonic rhythm: mean pitch-class-set turnover (Jaccard distance) between consecutive bars; fast-changing chords (jazz, gospel) vs static/drone harmony (folk, ambient, some rock)."""
    nb = song.n_bars
    if not nb or nb < 2:
        return 0.0
    prev = None
    dists = []
    for b in range(1, nb + 1):
        cur = set(song.bar_pcs(b))
        if prev is not None:
            u = prev | cur
            if u:
                inter = prev & cur
                dists.append(1.0 - len(inter) / len(u))
        prev = cur
    if not dists:
        return 0.0
    return float(np.mean(dists))


def axis_instrument_diversity(song) -> float:
    """Timbral variety: entropy of the instrument-program distribution weighted by each voice's onset count; big-band/orchestral spread across many timbres, solo/duo concentrate on few."""
    events = song.events
    programs = song.voice_programs
    if not events or not programs:
        return 0.0
    prog_onsets = collections.defaultdict(float)
    for e in events:
        v = e["voice"]
        p = programs.get(v)
        if p is None:
            continue
        prog_onsets[p] += 1.0
    tot = sum(prog_onsets.values())
    if tot <= 0:
        return 0.0
    h = 0.0
    for w in prog_onsets.values():
        p = w / tot
        h -= p * math.log(p)
    return h


def axis_leader_turnover(song) -> float:
    """Fraction of adjacent beats whose most-active pitched voice differs (lead/voice trading rate); call-and-response gospel/blues & contrapuntal jazz swap the spotlight, while pop/folk keep one fixed melody voice."""
    win = collections.defaultdict(collections.Counter)
    for e in song.events:
        if e["voice"] in song.drum_voices:
            continue
        w = math.floor(e["abs"])
        win[w][e["voice"]] += 1
    if len(win) < 2:
        return 0.0
    ws = sorted(win.keys())
    leaders = []
    for w in ws:
        c = win[w]
        leaders.append(max(c.items(), key=lambda kv: kv[1])[0])
    changes = sum(1 for i in range(1, len(leaders)) if leaders[i] != leaders[i - 1])
    return changes / (len(leaders) - 1)


def axis_legato_ratio(song) -> float:
    """Mean ratio of note duration to the gap until the next onset within each pitched voice (legato vs staccato articulation); sustained pad/string/ballad writing vs detached funk stabs & staccato comping."""
    ratios = []
    for v in song.voices:
        if v in song.drum_voices:
            continue
        evs = sorted(song.voice_events(v), key=lambda e: e["abs"])
        for i in range(len(evs) - 1):
            gap = evs[i + 1]["abs"] - evs[i]["abs"]
            if gap > 1e-6:
                ratios.append(min(evs[i]["dur"] / gap, 3.0))
    if not ratios:
        return 0.0
    return float(np.mean(ratios))


def axis_mean_note_length(song) -> float:
    """Mean note duration in beats (articulation/pacing); sustained legato writing (strings, ballads, pads) vs short detached notes (staccato comping, funk stabs, hi-hats)."""
    durs = [e["dur"] for e in song.events if e["dur"] > 0]
    if not durs:
        return 0.0
    return float(np.mean(durs))


def axis_melodic_interval_mean(song) -> float:
    """Mean absolute melodic interval (semitones) in the most active voice's monophonic line; stepwise folk/country vs leap-rich classical/jazz melodies."""
    v = song.most_active_voice()
    if v is None:
        return 0.0
    line = song.line(v)
    if not line:
        return 0.0
    times = sorted(line.keys())
    if len(times) < 2:
        return 0.0
    prev = line[times[0]]
    diffs = []
    for t in times[1:]:
        cur = line[t]
        diffs.append(abs(cur - prev))
        prev = cur
    if not diffs:
        return 0.0
    return float(np.mean(diffs))


def axis_mode_majorness(song) -> float:
    """Signed major-vs-minor tonal color: duration mass on the major 3rd minus the minor 3rd above the best-fit tonic, normalized; bright major pop/country/gospel vs darker minor latin/jazz/rock."""
    pcw = song.pc_weight()
    tot = sum(pcw.values())
    if tot <= 0:
        return 0.0
    best_root = 0
    best = -1.0
    for root in range(12):
        w = pcw.get(root, 0.0) + pcw.get((root + 7) % 12, 0.0)
        if w > best:
            best = w
            best_root = root
    maj = pcw.get((best_root + 4) % 12, 0.0)
    minr = pcw.get((best_root + 3) % 12, 0.0)
    return (maj - minr) / tot


def axis_note_density_bar_variability(song) -> float:
    """Coefficient of variation of per-bar onset counts (arrangement dynamics / build-and-drop contour); dynamically arranged electronic & orchestral music vs uniformly busy comping or steady grooves."""
    nb = song.n_bars
    if not nb or nb < 2:
        return 0.0
    counts = [0] * (nb + 1)
    for e in song.events:
        b = e["bar"]
        if 1 <= b <= nb:
            counts[b] += 1
    vals = counts[1:]
    if not vals:
        return 0.0
    m = float(np.mean(vals))
    if m <= 0:
        return 0.0
    return float(np.std(vals)) / m


def axis_offbeat_onset_ratio(song) -> float:
    """Fraction of note onsets falling off the main beat (syncopation density); jazz/funk/latin syncopate far more than folk/classical."""
    events = song.events
    if not events:
        return 0.0
    off = 0
    tot = 0
    for e in events:
        onb = e["onb"]
        frac = onb - math.floor(onb)
        # distance to nearest integer beat
        d = min(frac, 1.0 - frac)
        tot += 1
        if d > 0.08:
            off += 1
    if tot == 0:
        return 0.0
    return off / tot


def axis_onset_density(song) -> float:
    """Onset density: distinct note onsets per bar; busy/virtuosic textures vs sparse/ballad ones, normalized by song length."""
    nb = song.n_bars
    if not nb or nb <= 0:
        return 0.0
    return float(song.onset_count()) / float(nb)


def axis_onset_synchrony(song) -> float:
    """Fraction of onset instants where two or more pitched voices attack together (homophonic block-chord texture); gospel/hymn/classical chorales strike chords in unison, while jazz & contrapuntal writing stagger attacks."""
    groups = collections.defaultdict(set)
    for e in song.events:
        if e["voice"] in song.drum_voices:
            continue
        groups[round(e["abs"] * 4) / 4.0].add(e["voice"])
    if not groups:
        return 0.0
    multi = sum(1 for vs in groups.values() if len(vs) >= 2)
    return multi / len(groups)


def axis_pc_entropy(song) -> float:
    """Normalized Shannon entropy of the duration-weighted pitch-class profile; high = harmonically rich/chromatic (jazz), low = tonally focused (folk/pop)."""
    pcw = song.pc_weight()
    tot = sum(pcw.values())
    if tot <= 0:
        return 0.0
    h = 0.0
    for w in pcw.values():
        if w > 0:
            p = w / tot
            h -= p * math.log(p)
    return h / math.log(12)


def axis_pcs_per_bar(song) -> float:
    """Mean number of distinct pitch classes present per bar (harmonic/chromatic density within a measure); chord-rich jazz & gospel light up many pitch classes each bar, whereas riff- or drone-based folk/rock use few."""
    nb = song.n_bars
    if not nb or nb <= 0:
        return 0.0
    sizes = []
    for b in range(1, nb + 1):
        pcs = song.bar_pcs(b)
        if pcs:
            sizes.append(len(set(pcs)))
    if not sizes:
        return 0.0
    return float(np.mean(sizes))


def axis_polyphony(song) -> float:
    """Average polyphony: total sounding-note duration divided by the piece's time span (mean number of notes sounding at once); dense chordal texture vs sparse melody."""
    events = song.events
    if not events:
        return 0.0
    total_dur = 0.0
    lo = None
    hi = None
    for e in events:
        d = e["dur"]
        total_dur += d
        s = e["abs"]
        en = s + d
        if lo is None or s < lo:
            lo = s
        if hi is None or en > hi:
            hi = en
    span = (hi - lo) if (lo is not None and hi is not None) else 0.0
    if span <= 0:
        return 0.0
    return total_dur / span


def axis_power_chord_ratio(song) -> float:
    """Fraction of vertical sonorities that are bare open fifths/octaves lacking any third (power chords); distortion-friendly metal/hard-rock vs triadic folk/pop and 7th-rich jazz/gospel."""
    groups = collections.defaultdict(set)
    for e in song.events:
        if e["voice"] in song.drum_voices:
            continue
        groups[round(e["abs"] * 4) / 4.0].add(e["midi"])
    tot = 0
    power = 0
    for midis in groups.values():
        pcs = set(m % 12 for m in midis)
        if len(pcs) < 2:
            continue
        bass = min(midis) % 12
        ivs = set((p - bass) % 12 for p in pcs)
        tot += 1
        has_fifth = 7 in ivs
        has_third = (3 in ivs) or (4 in ivs)
        if has_fifth and not has_third:
            power += 1
    if tot == 0:
        return 0.0
    return power / tot


def axis_register_center(song) -> float:
    """Registral center: mean MIDI pitch across all notes; bass-heavy/low arrangements vs bright treble-dominated ones."""
    midis = song.midis()
    if not midis:
        return 0.0
    return float(np.mean(midis))


def axis_repeated_note_ratio(song) -> float:
    """Fraction of consecutive melody notes that repeat the same pitch in the most-active voice (declamatory/chant-like delivery); repeated-note gospel & soul vocal lines and rap-like phrasing vs the stepwise melodic motion of folk/country and classical."""
    v = song.most_active_voice()
    if v is None:
        return 0.0
    line = song.line(v)
    if not line:
        return 0.0
    times = sorted(line.keys())
    if len(times) < 2:
        return 0.0
    same = 0
    tot = 0
    prev = line[times[0]]
    for t in times[1:]:
        cur = line[t]
        tot += 1
        if cur == prev:
            same += 1
        prev = cur
    if tot == 0:
        return 0.0
    return same / tot


def axis_seventh_chord_ratio(song) -> float:
    """Fraction of vertical sonorities that stack a seventh above the bass (extended tertian harmony); jazz/gospel 7th-9th chords vs the plain triads of folk/classical/pop."""
    groups = collections.defaultdict(list)
    for e in song.events:
        if e["voice"] in song.drum_voices:
            continue
        groups[round(e["abs"] * 4) / 4.0].append(e["midi"])
    tot = 0
    sev = 0
    for midis in groups.values():
        pcs = set(m % 12 for m in midis)
        if len(pcs) < 3:
            continue
        bass = min(midis) % 12
        ivs = set((p - bass) % 12 for p in pcs)
        tot += 1
        has_third = (3 in ivs) or (4 in ivs)
        has_seventh = (10 in ivs) or (11 in ivs)
        if has_third and has_seventh:
            sev += 1
    if tot == 0:
        return 0.0
    return sev / tot


def axis_swing_ratio(song) -> float:
    """Swing feel: share of intra-beat onsets closer to a triplet subdivision (0.33/0.67) than a straight eighth (0.5); jazz/blues/shuffle swing, pop/classical play straight."""
    events = song.events
    swing = 0
    straight = 0
    for e in events:
        frac = e["onb"] - math.floor(e["onb"])
        if frac < 0.12 or frac > 0.88:
            continue  # on-beat, not a subdivision
        ds = abs(frac - 0.5)
        dsw = min(abs(frac - 0.667), abs(frac - 0.333))
        if dsw < ds:
            swing += 1
        else:
            straight += 1
    tot = swing + straight
    if tot == 0:
        return 0.0
    return swing / tot


def axis_tertian_stack_depth(song) -> float:
    """Average number of distinct tertian chord degrees stacked above the bass (3rd, 5th, 7th, 9th, 11th, 13th) across vertical sonorities; extended jazz/gospel voicings pile up 7ths/9ths/13ths while folk/pop stop at the triad — a harmonic-extension depth that should correlate with the CE/PC audiobox anchors."""
    groups = collections.defaultdict(list)
    for e in song.events:
        if e["voice"] in song.drum_voices:
            continue
        groups[round(e["abs"] * 4) / 4.0].append(e["midi"])
    # tertian degree intervals (mod 12): 3rd(3/4), 5th(7), 7th(10/11), 9th(2/1), 11th(5/6), 13th(9/8)
    degree_sets = [(3, 4), (7,), (10, 11), (1, 2), (5, 6), (8, 9)]
    depths = []
    for midis in groups.values():
        pcs = set(m % 12 for m in midis)
        if len(pcs) < 2:
            continue
        bass = min(midis) % 12
        ivs = set((p - bass) % 12 for p in pcs if (p - bass) % 12 != 0)
        d = sum(1 for degs in degree_sets if any(iv in ivs for iv in degs))
        depths.append(d)
    if not depths:
        return 0.0
    return float(np.mean(depths))


def axis_tonic_pedal_fraction(song) -> float:
    """Share of the bass voice's total note duration spent on its single most-used pitch class (root pedal / drone strength); riff- and drone-based folk/rock hammer one bass note, whereas walking-bass jazz & funk keep moving."""
    by = collections.defaultdict(list)
    for e in song.events:
        if e["voice"] in song.drum_voices:
            continue
        by[e["voice"]].append(e)
    if not by:
        return 0.0
    bassv = min(by.keys(), key=lambda v: float(np.mean([x["midi"] for x in by[v]])))
    dur = collections.defaultdict(float)
    for e in by[bassv]:
        dur[e["pc"]] += max(e["dur"], 0.0)
    tot = sum(dur.values())
    if tot <= 0:
        return 0.0
    return max(dur.values()) / tot


def axis_velocity_dynamic_range(song) -> float:
    """Dynamic range: standard deviation of note velocities; expressive/rubato genres (classical, jazz) vary loudness, machine-programmed genres (EDM, some pop) stay flat."""
    vels = [float(e.get("vel", 64)) for e in song.events]
    if len(vels) < 2:
        return 0.0
    return float(np.std(vels))


def axis_velocity_jitter(song) -> float:
    """Mean absolute velocity change between temporally consecutive onsets (note-to-note dynamic jitter / touch expressivity); humanly-played classical & jazz vary loudness note-by-note, while machine-programmed electronic/pop stay flat (distinct from the global velocity spread)."""
    evs = sorted(song.events, key=lambda e: e["abs"])
    vels = [float(e.get("vel", 64)) for e in evs]
    if len(vels) < 2:
        return 0.0
    diffs = [abs(vels[i] - vels[i - 1]) for i in range(1, len(vels))]
    return float(np.mean(diffs))


def axis_voice_register_separation(song) -> float:
    """Spread (std) of the mean pitch of each non-drum voice; wide-registral arrangements with distinct bass/mid/lead layers vs clustered close-position textures."""
    by = collections.defaultdict(list)
    for e in song.events:
        if e["voice"] in song.drum_voices:
            continue
        by[e["voice"]].append(e["midi"])
    means = [float(np.mean(v)) for v in by.values() if v]
    if len(means) < 2:
        return 0.0
    return float(np.std(means))


REGISTRY = {
    'axis_active_voice_count': axis_active_voice_count,
    'axis_backbeat_emphasis': axis_backbeat_emphasis,
    'axis_bar_pitch_range_mean': axis_bar_pitch_range_mean,
    'axis_bass_register_gap': axis_bass_register_gap,
    'axis_bass_syncopation': axis_bass_syncopation,
    'axis_bass_walk_rate': axis_bass_walk_rate,
    'axis_blue_note_content': axis_blue_note_content,
    'axis_chord_simultaneity_size': axis_chord_simultaneity_size,
    'axis_chord_type_diversity': axis_chord_type_diversity,
    'axis_chromaticism': axis_chromaticism,
    'axis_contour_reversal_rate': axis_contour_reversal_rate,
    'axis_dissonant_interval_ratio': axis_dissonant_interval_ratio,
    'axis_drum_ratio': axis_drum_ratio,
    'axis_drum_timbre_entropy': axis_drum_timbre_entropy,
    'axis_duration_cv': axis_duration_cv,
    'axis_harmonic_rhythm': axis_harmonic_rhythm,
    'axis_instrument_diversity': axis_instrument_diversity,
    'axis_leader_turnover': axis_leader_turnover,
    'axis_legato_ratio': axis_legato_ratio,
    'axis_mean_note_length': axis_mean_note_length,
    'axis_melodic_interval_mean': axis_melodic_interval_mean,
    'axis_mode_majorness': axis_mode_majorness,
    'axis_note_density_bar_variability': axis_note_density_bar_variability,
    'axis_offbeat_onset_ratio': axis_offbeat_onset_ratio,
    'axis_onset_density': axis_onset_density,
    'axis_onset_synchrony': axis_onset_synchrony,
    'axis_pc_entropy': axis_pc_entropy,
    'axis_pcs_per_bar': axis_pcs_per_bar,
    'axis_polyphony': axis_polyphony,
    'axis_power_chord_ratio': axis_power_chord_ratio,
    'axis_register_center': axis_register_center,
    'axis_repeated_note_ratio': axis_repeated_note_ratio,
    'axis_seventh_chord_ratio': axis_seventh_chord_ratio,
    'axis_swing_ratio': axis_swing_ratio,
    'axis_tertian_stack_depth': axis_tertian_stack_depth,
    'axis_tonic_pedal_fraction': axis_tonic_pedal_fraction,
    'axis_velocity_dynamic_range': axis_velocity_dynamic_range,
    'axis_velocity_jitter': axis_velocity_jitter,
    'axis_voice_register_separation': axis_voice_register_separation,
}


def metrics_for(song, path=None, base_only=False):
    """Compute all v3 axes for a song -> {axis_name: float}. path/base_only kept for API compat."""
    out = {}
    for name, fn in REGISTRY.items():
        try:
            v = float(fn(song)); out[name] = v if math.isfinite(v) else 0.0
        except Exception:
            out[name] = 0.0
    return out
