#!/usr/bin/env python3
"""levers.py — per-axis grammar perturbations for external axis validation, with an extensible registry.

A *lever* is a function ``fn(grammar_text, dose) -> grammar_text`` that nudges ONE target axis (a key of
``libretto.core.metric_discovery.metrics_for``) toward an extreme, monotonically in ``dose`` in ``[0, 1]``
(0 = unchanged, 1 = strongest push). Levers hold *content/instrumentation* fixed and vary *structure* along
one axis, so an independent judge (see ``libretto.validation.judge``) can be watched for a dose-response.

Register your own axis with the decorator::

    from libretto.validation import lever

    @lever("my_axis", push="high")
    def push_my_axis(text, dose):
        ...                     # edit the grammar text toward the axis's high extreme
        return new_text

or programmatically with ``register_lever("my_axis", "high", fn)``. The validator re-fingerprints every
output, so it will tell you whether your lever actually moved the target axis and how many OTHER axes it
dragged along (entanglement) — a clean lever moves its target and little else.

WHY 25 OF THE 29 CANONICAL AXES HAVE A LEVER (and 4 do not): see ``UNCOVERED`` below. The four omitted axes
are emergent statistics over the whole chord-set / self-similarity structure with no isolated grammatical
handle — any edit that moves them also strongly moves several correlated axes, so a single-axis dose-response
is impossible. They remain valid descriptive coordinates; they just cannot be *causally* externalised this way.
"""
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable

from libretto.core.understanding_probe import parse_pitch_midi, _midi_name

# match Pitch@slot>dur with an OPTIONAL ^velocity suffix — the current (enriched) grammar carries velocity
# (e.g. A3+C4@1>4^80); without this the token fails to parse, tokens() returns empty, and edit_tokens
# DROPS the whole voice line -> the grammar collapses. Velocity is not captured here (levers hold the render
# fixed and only perturb structure, so velocity is uniform across doses); it is simply no longer a parse-blocker.
_TOKEN_RE = re.compile(r"^(.+)@(\d+)>(\d+)(?:\^\d+)?$")
_GRID_RE = re.compile(r"\(grid:\d+t?\)")


# --------------------------------------------------------------------------- #
# registry
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Lever:
    axis: str
    push: str               # "high" or "low" — the extreme this lever drives the axis toward
    fn: Callable            # fn(text, dose) -> text


LEVERS: dict[str, Lever] = {}


def register_lever(axis: str, push: str, fn: Callable) -> Callable:
    """Register (or override) a lever for ``axis`` pushing toward ``push`` ('high'|'low')."""
    if push not in ("high", "low"):
        raise ValueError(f"push must be 'high' or 'low', got {push!r}")
    LEVERS[axis] = Lever(axis=axis, push=push, fn=fn)
    return fn


def lever(axis: str, push: str):
    """Decorator form of :func:`register_lever`."""
    def deco(fn):
        register_lever(axis, push, fn)
        return fn
    return deco


def perturb(text: str, axis: str, dose: float) -> str:
    """Apply ``axis``'s lever at ``dose``. dose<=0 returns the text unchanged."""
    if axis not in LEVERS:
        raise KeyError(f"no lever registered for axis {axis!r}; have {sorted(LEVERS)}")
    if dose <= 0:
        return text
    return LEVERS[axis].fn(text, float(dose))


# --------------------------------------------------------------------------- #
# text surgery (operate on grammar text only; always emit a valid grammar)
# --------------------------------------------------------------------------- #
def split_blocks(text):
    head, blocks, cur = [], [], None
    for ln in text.splitlines():
        if ln.startswith("@"):
            if cur is not None:
                blocks.append(cur)
            cur = [ln]
        elif cur is None:
            head.append(ln)
        else:
            cur.append(ln)
    if cur is not None:
        blocks.append(cur)
    return head, blocks


def join(head, blocks):
    out = list(head)
    for blk in blocks:
        out.extend(blk)
    return "\n".join(out) + "\n"


def voice_name(line):
    return line.partition(":")[0].strip() if ":" in line else None


def is_voice_line(line):
    return ":" in line and not line.startswith("@")


def tokens(line):
    _, _, rest = line.partition(":")
    for tok in rest.split():
        m = _TOKEN_RE.match(tok)
        if m:
            yield m.group(1), int(m.group(2)), int(m.group(3))


def rebuild(line, toks):
    head = line.partition(":")[0]
    body = " ".join(f"{p}@{on}>{du}" for p, on, du in toks)
    return f"{head}: {body}"


def _seeded_rng(text, salt):
    import random
    return random.Random(hash((len(text), text[:64], salt)) & 0xFFFFFFFF)


def map_pitches(pstr, fn):
    """Apply fn(midi)->midi to each pitch in a (possibly chord) token; non-pitches pass through."""
    out = []
    for sub in pstr.split("+"):
        m = parse_pitch_midi(sub)
        if m is None:
            out.append(sub)
        else:
            nm = fn(m)
            if nm is not None:
                out.append(_midi_name(max(0, min(127, int(round(nm))))))
    return "+".join(out) if out else None


def voice_means(text):
    acc = defaultdict(lambda: [0, 0])
    _, blocks = split_blocks(text)
    for blk in blocks:
        for ln in blk[1:]:
            if not is_voice_line(ln):
                continue
            v = voice_name(ln)
            for p, _, _ in tokens(ln):
                for sub in p.split("+"):
                    m = parse_pitch_midi(sub)
                    if m is not None:
                        acc[v][0] += m
                        acc[v][1] += 1
    return {v: s / n for v, (s, n) in acc.items() if n}


def melody_voice(text):
    mv = voice_means(text)
    return max(mv, key=mv.get) if mv else None


def bass_voice(text):
    mv = voice_means(text)
    return min(mv, key=mv.get) if mv else None


def edit_tokens(text, fn, voices=None):
    """fn(voice, [(p,on,du),...]) -> new list. Empty result drops the voice line for that bar."""
    head, blocks = split_blocks(text)
    for blk in blocks:
        nb = [blk[0]]
        for ln in blk[1:]:
            if not is_voice_line(ln):
                nb.append(ln)
                continue
            v = voice_name(ln)
            if voices and v not in voices:
                nb.append(ln)
                continue
            nt = fn(v, list(tokens(ln)))
            if nt:
                nb.append(rebuild(ln, nt))
        blk[:] = nb
    return join(head, blocks)


def _template(blocks):
    """Voice lines of the first bar that HAS any (some songs open with an empty pickup bar)."""
    for blk in blocks:
        v = [ln for ln in blk[1:] if is_voice_line(ln)]
        if v:
            return v
    return []


# --------------------------------------------------------------------------- #
# RHYTHM
# --------------------------------------------------------------------------- #
@lever("rhy_syncopation_rate", "high")
def lever_syncopation_up(text, dose):
    """Shift a `dose` fraction of onsets by +1 grid slot (off the beat)."""
    rng = _seeded_rng(text, "synco")
    def fn(v, toks):
        return [(p, on + 1, du) if rng.random() < dose else (p, on, du) for p, on, du in toks]
    return edit_tokens(text, fn)


@lever("rhy_onset_density_per_bar", "low")
def lever_onset_density_down(text, dose):
    """Delete a `dose` fraction of notes (keep >=1 per voice-line)."""
    rng = _seeded_rng(text, "density")
    def fn(v, toks):
        if len(toks) <= 1:
            return toks
        keep = [t for t in toks if rng.random() >= dose]
        return keep or [toks[0]]
    return edit_tokens(text, fn)


@lever("rhy_triplet_share", "high")
def lever_triplet_share_up(text, dose):
    """Mark a `dose` fraction of bars with a triplet grid tag."""
    rng = _seeded_rng(text, "trip")
    head, blocks = split_blocks(text)
    for blk in blocks:
        if rng.random() < dose:
            h = blk[0]
            blk[0] = _GRID_RE.sub("(grid:12t)", h) if _GRID_RE.search(h) else h.rstrip() + " (grid:12t)"
    return join(head, blocks)


@lever("rhy_onset_pos_entropy", "low")
def lever_onset_pos_entropy_down(text, dose):
    """Snap a `dose` fraction of onsets to slot 1 (collapse positions)."""
    rng = _seeded_rng(text, "posent")
    def fn(v, toks):
        return [(p, 1, du) if rng.random() < dose else (p, on, du) for p, on, du in toks]
    return edit_tokens(text, fn)


@lever("rhy_dur_cv", "low")
def lever_dur_cv_down(text, dose):
    """Pull a `dose` fraction of durations toward the global mean (uniformer lengths)."""
    durs = [du for blk in split_blocks(text)[1] for ln in blk[1:]
            if is_voice_line(ln) for _, _, du in tokens(ln)]
    mean = max(1, round(sum(durs) / len(durs))) if durs else 1
    rng = _seeded_rng(text, "durcv")
    def fn(v, toks):
        return [(p, on, mean) if rng.random() < dose else (p, on, du) for p, on, du in toks]
    return edit_tokens(text, fn)


@lever("rhy_mean_dur_beats", "high")
def lever_mean_dur_up(text, dose):
    """Lengthen every note: dur *= (1 + 3*dose)."""
    factor = 1.0 + 3.0 * dose
    def fn(v, toks):
        return [(p, on, max(1, round(du * factor))) for p, on, du in toks]
    return edit_tokens(text, fn)


@lever("rhy_density_variability", "high")
def lever_density_variability_up(text, dose):
    """Thin a `dose`-scaled fraction of bars to ~1 note/voice (alternating sparse/full bars raise the
    per-bar onset-count variance). Fraction capped at 0.5 (thinning ALL bars makes density uniformly low)."""
    rng = _seeded_rng(text, "densvar")
    head, blocks = split_blocks(text)
    frac = 0.5 * dose
    for j, blk in enumerate(blocks):
        if j > 0 and rng.random() < frac:
            for i, ln in enumerate(blk[1:], 1):
                if is_voice_line(ln):
                    toks = list(tokens(ln))
                    if toks:
                        blk[i] = rebuild(ln, [toks[0]])
    return join(head, blocks)


# --------------------------------------------------------------------------- #
# HARMONY
# --------------------------------------------------------------------------- #
@lever("har_chromaticism", "high")
def lever_chromaticism_up(text, dose):
    """Raise a fraction (capped 0.5: all-shift = transposition) by +1 semitone."""
    frac = 0.5 * dose
    rng = _seeded_rng(text, "chroma")
    def fn(v, toks):
        return [(map_pitches(p, lambda m: m + 1) or p, on, du) if rng.random() < frac else (p, on, du)
                for p, on, du in toks]
    return edit_tokens(text, fn)


@lever("har_distinct_pc", "low")
def lever_distinct_pc_down(text, dose):
    """Remap a `dose` fraction of notes to the nearest of a 3-pc set {C,E,G}."""
    allowed = (0, 4, 7)
    rng = _seeded_rng(text, "distpc")
    def snap(m):
        pc = m % 12
        best = min(allowed, key=lambda a: min((pc - a) % 12, (a - pc) % 12))
        return m - pc + best
    def fn(v, toks):
        return [(map_pitches(p, snap) or p, on, du) if rng.random() < dose else (p, on, du)
                for p, on, du in toks]
    return edit_tokens(text, fn)


@lever("har_pc_entropy", "low")
def lever_pc_entropy_down(text, dose):
    """Force a `dose` fraction of notes to pitch-class C (concentrate weight)."""
    rng = _seeded_rng(text, "pcent")
    def toC(m):
        return m - (m % 12)
    def fn(v, toks):
        return [(map_pitches(p, toC) or p, on, du) if rng.random() < dose else (p, on, du)
                for p, on, du in toks]
    return edit_tokens(text, fn)


@lever("har_root_motion_entropy", "low")
def lever_root_motion_entropy_down(text, dose):
    """Flatten the bass: set a `dose` fraction of bass notes to its modal pitch (less root motion)."""
    bass = bass_voice(text)
    if not bass:
        return text
    pitches = [parse_pitch_midi(s) for blk in split_blocks(text)[1]
               for ln in blk[1:] if is_voice_line(ln) and voice_name(ln) == bass
               for p, _, _ in tokens(ln) for s in p.split("+") if parse_pitch_midi(s) is not None]
    if not pitches:
        return text
    mode = max(set(pitches), key=pitches.count)
    rng = _seeded_rng(text, "rootent")
    def fn(v, toks):
        return [(_midi_name(mode), on, du) if rng.random() < dose else (p, on, du) for p, on, du in toks]
    return edit_tokens(text, fn, voices={bass})


@lever("har_dimaug_rate", "high")
def lever_dimaug_up(text, dose):
    """Inject a sustained diminished triad (C+Eb+Gb) into a `dose` fraction of bars so it dominates the
    bar's pitch-class weight (the metric's prominence test is 30% of max weight)."""
    rng = _seeded_rng(text, "dimaug")
    head, blocks = split_blocks(text)
    for blk in blocks:
        if rng.random() >= dose:
            continue
        for i, ln in enumerate(blk[1:], 1):
            if is_voice_line(ln):
                blk[i] = rebuild(ln, [("C4+Eb4+Gb4", 1, 8)])
                break
    return join(head, blocks)


# --------------------------------------------------------------------------- #
# MELODY (operate on the melody voice = highest mean pitch)
# --------------------------------------------------------------------------- #
@lever("mel_pitch_range", "high")
def lever_pitch_range_up(text, dose):
    """Transpose the highest-mean voice up and the lowest-mean voice down by round(12*dose) semitones."""
    semi = round(12 * dose)
    if semi == 0:
        return text
    mv = voice_means(text)
    if len(mv) < 2:
        return text
    hi_v, lo_v = max(mv, key=mv.get), min(mv, key=mv.get)
    shift = {hi_v: +semi, lo_v: -semi}
    def fn(v, toks):
        d = shift.get(v, 0)
        if d == 0:
            return toks
        return [(map_pitches(p, lambda m: m + d) or p, on, du) for p, on, du in toks]
    return edit_tokens(text, fn, voices=set(shift))


@lever("mel_step_ratio", "high")
def lever_step_ratio_up(text, dose):
    """Pull a `dose` fraction of melody notes to within 2 semitones of the previous note (stepwise)."""
    mel = melody_voice(text)
    if not mel:
        return text
    rng = _seeded_rng(text, "step")
    head, blocks = split_blocks(text)
    prev = [None]
    for blk in blocks:
        for i, ln in enumerate(blk[1:], 1):
            if not (is_voice_line(ln) and voice_name(ln) == mel):
                continue
            nt = []
            for p, on, du in tokens(ln):
                m = parse_pitch_midi(p.split("+")[0])
                if m is not None and prev[0] is not None and rng.random() < dose:
                    m = prev[0] + max(-2, min(2, m - prev[0])) if m != prev[0] else prev[0] + 1
                    p = _midi_name(max(0, min(127, m)))
                if m is not None:
                    prev[0] = m
                nt.append((p, on, du))
            blk[i] = rebuild(ln, nt)
    return join(head, blocks)


@lever("mel_interval_entropy", "low")
def lever_interval_entropy_down(text, dose):
    """Force a `dose` fraction of melody steps to a constant +2 interval."""
    mel = melody_voice(text)
    if not mel:
        return text
    rng = _seeded_rng(text, "ivent")
    head, blocks = split_blocks(text)
    prev = [None]
    for blk in blocks:
        for i, ln in enumerate(blk[1:], 1):
            if not (is_voice_line(ln) and voice_name(ln) == mel):
                continue
            nt = []
            for p, on, du in tokens(ln):
                m = parse_pitch_midi(p.split("+")[0])
                if m is not None and prev[0] is not None and rng.random() < dose:
                    m = prev[0] + 2
                    p = _midi_name(max(0, min(127, m)))
                if m is not None:
                    prev[0] = m
                nt.append((p, on, du))
            blk[i] = rebuild(ln, nt)
    return join(head, blocks)


@lever("mel_up_ratio", "high")
def lever_up_ratio_up(text, dose):
    """Force a `dose` fraction of melody steps to go upward."""
    mel = melody_voice(text)
    if not mel:
        return text
    rng = _seeded_rng(text, "up")
    head, blocks = split_blocks(text)
    prev = [None]
    for blk in blocks:
        for i, ln in enumerate(blk[1:], 1):
            if not (is_voice_line(ln) and voice_name(ln) == mel):
                continue
            nt = []
            for p, on, du in tokens(ln):
                m = parse_pitch_midi(p.split("+")[0])
                if m is not None and prev[0] is not None and rng.random() < dose and m <= prev[0]:
                    m = prev[0] + 2
                    p = _midi_name(max(0, min(127, m)))
                if m is not None:
                    prev[0] = m
                nt.append((p, on, du))
            blk[i] = rebuild(ln, nt)
    return join(head, blocks)


@lever("mel_voice_range", "high")
def lever_voice_range_up(text, dose):
    """Expand the melody voice around its mean (scale intervals by 1+3*dose)."""
    mel = melody_voice(text)
    if not mel:
        return text
    mean = voice_means(text)[mel]
    factor = 1.0 + 3.0 * dose
    def fn(v, toks):
        return [(map_pitches(p, lambda m: mean + (m - mean) * factor) or p, on, du) for p, on, du in toks]
    return edit_tokens(text, fn, voices={mel})


# --------------------------------------------------------------------------- #
# TEXTURE
# --------------------------------------------------------------------------- #
@lever("tex_voice_count", "low")
def lever_voice_count_down(text, dose):
    """Drop a `dose` fraction of voices entirely (keep >=1)."""
    rng = _seeded_rng(text, "voices")
    head, blocks = split_blocks(text)
    voices = []
    for blk in blocks:
        for ln in blk[1:]:
            if is_voice_line(ln) and voice_name(ln) not in voices:
                voices.append(voice_name(ln))
    if len(voices) <= 1:
        return text
    drop = {v for v in voices if rng.random() < dose}
    drop = set(list(drop)[: len(voices) - 1])  # always keep at least one
    for blk in blocks:
        blk[1:] = [ln for ln in blk[1:] if not (is_voice_line(ln) and voice_name(ln) in drop)]
    return join(head, blocks)


@lever("tex_mean_simultaneity", "high")
def lever_mean_simultaneity_up(text, dose):
    """Thicken a `dose` fraction of notes into a 2-note chord (+third)."""
    rng = _seeded_rng(text, "simul")
    def fn(v, toks):
        out = []
        for p, on, du in toks:
            if rng.random() < dose:
                m = parse_pitch_midi(p.split("+")[0])
                if m is not None:
                    p = p + "+" + _midi_name(min(127, m + 4))
            out.append((p, on, du))
        return out
    return edit_tokens(text, fn)


@lever("tex_max_chord_width", "high")
def lever_max_chord_width_up(text, dose):
    """Add a far note (octaves set by dose) to the first chord of each bar."""
    span = 12 + round(24 * dose)
    head, blocks = split_blocks(text)
    for blk in blocks:
        for i, ln in enumerate(blk[1:], 1):
            if is_voice_line(ln):
                toks = list(tokens(ln))
                if toks:
                    p, on, du = toks[0]
                    m = parse_pitch_midi(p.split("+")[0])
                    if m is not None:
                        toks[0] = (p + "+" + _midi_name(min(127, m + span)), on, du)
                        blk[i] = rebuild(ln, toks)
                break
    return join(head, blocks)


@lever("tex_active_voice_density", "low")
def lever_active_voice_density_down(text, dose):
    """In a `dose` fraction of bars, keep only the first voice line."""
    rng = _seeded_rng(text, "actvd")
    head, blocks = split_blocks(text)
    for blk in blocks:
        if rng.random() < dose:
            vlines = [ln for ln in blk[1:] if is_voice_line(ln)]
            if len(vlines) > 1:
                blk[1:] = vlines[:1]
    return join(head, blocks)


# --------------------------------------------------------------------------- #
# FORM / WITHIN-SONG
# --------------------------------------------------------------------------- #
@lever("form_self_similarity", "high")
def lever_self_similarity_up(text, dose):
    """Overwrite a `dose` fraction of bars (after bar 1) with bar-1 content."""
    rng = _seeded_rng(text, "selfsim")
    head, blocks = split_blocks(text)
    tmpl = _template(blocks)
    if len(blocks) < 2 or not tmpl:
        return text
    for blk in blocks[1:]:
        if rng.random() < dose:
            blk[1:] = list(tmpl)
    return join(head, blocks)


@lever("form_novelty_rate", "low")
def lever_novelty_rate_down(text, dose):
    """Copy the previous bar's content into a `dose` fraction of bars (adjacent bars become identical)."""
    rng = _seeded_rng(text, "novelty")
    head, blocks = split_blocks(text)
    for j in range(1, len(blocks)):
        if rng.random() < dose:
            prev_voice = [ln for ln in blocks[j - 1][1:] if is_voice_line(ln)]
            if prev_voice:
                blocks[j][1:] = list(prev_voice)
    return join(head, blocks)


@lever("form_distinct_bar_frac", "low")
def lever_distinct_bar_frac_down(text, dose):
    """Replace a `dose` fraction of bars with the bar-1 template (fewer distinct bar contents)."""
    rng = _seeded_rng(text, "distbar")
    head, blocks = split_blocks(text)
    tmpl = _template(blocks)
    if not tmpl:
        return text
    for blk in blocks[1:]:
        if rng.random() < dose:
            blk[1:] = list(tmpl)
    return join(head, blocks)


@lever("within_song_variation", "low")
def lever_within_song_variation_down(text, dose):
    """Make local character uniform by overwriting a `dose` fraction of bars with the bar-1 template."""
    rng = _seeded_rng(text, "wsv")
    head, blocks = split_blocks(text)
    tmpl = _template(blocks)
    if not tmpl:
        return text
    for blk in blocks[1:]:
        if rng.random() < dose:
            blk[1:] = list(tmpl)
    return join(head, blocks)


# --------------------------------------------------------------------------- #
# axes intentionally WITHOUT a lever — emergent chord-set / SSM structure with no isolated handle.
# Perturbing them requires a coherent global rewrite that drags many correlated axes along, so a clean
# single-axis dose-response (and thus honest attribution) is impossible. They are still valid descriptive
# coordinates; they simply cannot be CAUSALLY externalised by local perturbation.
# --------------------------------------------------------------------------- #
UNCOVERED: dict[str, str] = {
    "har_chord_change_rate":
        "harmonic-rhythm statistic: changing how often the chord (pitch-class set) turns over requires "
        "rewriting all voices together, which also moves pc-entropy, simultaneity and root motion.",
    "har_vocab_density":
        "size/density of the distinct chord vocabulary — emergent from the whole chord set; altering it "
        "redesigns the harmony, dragging distinct-pc, chromaticism and pc-entropy.",
    "har_fourth_motion_rate":
        "fraction of root motions by a fourth/fifth — needs a coherent bass-root rewrite that entangles "
        "root-motion-entropy and the harmonic skeleton.",
    "form_section_per100bars":
        "section count from the self-similarity matrix — a whole-piece segmentation statistic; you cannot "
        "insert a section boundary locally without restructuring repetition (moves self-similarity, "
        "novelty, distinct-bar-fraction).",
}
