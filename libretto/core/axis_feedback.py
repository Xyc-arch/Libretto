#!/usr/bin/env python3
"""axis_feedback.py — turn a fingerprint axis + a direction into a precise, GROUNDED refinement signal.

The band engine reports which axes are out of band and which way to move (LOW -> raise, HIGH -> lower).
Two ways to hand that to a generator:
  (1) prescribe the fix in music terms ("voice fuller block chords") — risks misleading a capable model;
  (2) state WHAT the axis measures, WHERE the piece sits vs real songs, and WHICH way to move — and let the
      model decide HOW to realise it musically.
We use (2): each axis gets a short definition; the loop fills in the current percentile + target band +
direction. This is the most actionable, model-agnostic refinement signal (numbers + meaning + direction),
not a hard-coded musical prescription.
"""

# axis -> (readable name, one-line definition of WHAT it measures)
AXIS_DEF = {
    "rhy_syncopation_rate": ("syncopation", "how often notes fall off the beat"),
    "rhy_onset_density_per_bar": ("note density", "how many note onsets per bar"),
    "rhy_triplet_share": ("triplet feel", "how much of the piece is triplet/swung"),
    "rhy_onset_pos_entropy": ("rhythmic-placement variety", "how varied the rhythmic positions of onsets are"),
    "rhy_dur_cv": ("duration contrast", "how much note durations vary"),
    "rhy_mean_dur_beats": ("average note length", "the mean note duration"),
    "rhy_density_variability": ("density variation", "how much note-density changes across the piece"),
    "har_chromaticism": ("chromaticism", "how much out-of-key (chromatic) pitch is used"),
    "har_distinct_pc": ("pitch-class breadth", "how many distinct pitch classes are used"),
    "har_pc_entropy": ("pitch-class balance", "how evenly the pitch classes are used"),
    "har_chord_change_rate": ("harmonic rhythm", "how often the chord changes"),
    "har_vocab_density": ("chord variety", "how many distinct chords are used"),
    "har_root_motion_entropy": ("root-motion variety", "how varied the chord-root motion is"),
    "har_fourth_motion_rate": ("fourth/fifth motion", "how much the chord roots move by fourths/fifths"),
    "har_dimaug_rate": ("diminished/augmented colour", "how often diminished or augmented chords appear"),
    "mel_pitch_range": ("melodic range", "the overall melodic pitch span"),
    "mel_step_ratio": ("stepwise motion", "how much the melody moves by step vs by leap"),
    "mel_interval_entropy": ("interval variety", "how varied the melodic intervals are"),
    "mel_up_ratio": ("melodic direction", "how much the melody ascends vs descends"),
    "mel_voice_range": ("per-voice range", "the pitch span within each voice"),
    "tex_voice_count": ("voice count", "how many voices/parts there are"),
    "tex_mean_simultaneity": ("texture fullness", "how many notes sound at once"),
    "tex_max_chord_width": ("chord width", "the widest chord interval span"),
    "tex_active_voice_density": ("active voices", "how many voices are active at once"),
    "form_self_similarity": ("repetition", "how much material repeats"),
    "form_novelty_rate": ("novelty over time", "how much new material appears as the piece develops"),
    "form_distinct_bar_frac": ("bar distinctness", "the fraction of bars that are distinct from each other"),
    "form_section_per100bars": ("sectioning", "how many distinct sections per 100 bars"),
    "within_song_variation": ("within-song variation", "how much the local character drifts across the piece"),
}

_RAISE = {"increase", "raise", "higher", "low", "lo", "up", "LOW"}
_LOWER = {"decrease", "reduce", "lower", "high", "hi", "down", "HIGH"}


def musical_name(axis):
    return AXIS_DEF.get(axis, (axis.split("_", 1)[-1], ""))[0]


def explain(axis, direction, pct=None, lo=25, hi=75):
    """Grounded, non-prescriptive refinement line: WHAT the axis is, WHERE the piece sits, WHICH way to move.
    `pct` = the piece's current percentile vs the corpus (optional). The model chooses HOW to realise it."""
    name, defn = AXIS_DEF.get(axis, (axis.split("_", 1)[-1], ""))
    verb = "raise" if direction in _RAISE else ("lower" if direction in _LOWER else "move")
    # Drop the global-percentile clause if it would contradict the direction (split axes are judged vs the
    # GENRE band, where the global percentile can disagree) — keep the displayed number honest.
    if pct is not None and ((verb == "raise" and pct >= 50) or (verb == "lower" and pct <= 50)):
        pct = None
    here = f" — now ~{int(round(pct))}th pct of real songs" if pct is not None else ""
    label = f"{name} ({defn})" if defn else name
    return f"{label}{here}: {verb} it toward the typical {lo}–{hi}th-percentile range (you choose how)."


def explain_extreme(axis, percentile):
    """For a degenerate axis at a marginal extreme: <=5 -> raise, >=95 -> lower."""
    return explain(axis, "increase" if percentile <= 50 else "decrease", pct=percentile)
