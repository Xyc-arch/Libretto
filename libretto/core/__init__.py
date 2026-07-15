"""libretto.core — the deterministic measurement + tooling layer (reproducible).

Every symbol here is pure-Python and frozen against the packaged data version. No LLM.
"""
from .understanding_probe import Song
from .axes_v3 import metrics_for                # v3: 33 discovered axes (was metric_discovery's 28)
from .within_song_variation import wsv
from .copy_risk import copy_risk, piece_notes, slide_overlap
from .grammar_to_midi import decode as decode_to_midi
from .midi_to_grammar import encode as encode_from_midi
# self-evolving-loop per-round engine (fingerprint -> out-of-band axes -> dosage direction -> converge):
from .band_check import profile as band_profile, status as band_status   # GLOBAL idiomatic band
from . import genre_band_check                                           # general, genre-ADAPTIVE band
from . import axis_feedback                                              # axis -> musical instruction (loop feedback)

__all__ = [
    "Song", "metrics_for", "wsv",
    "copy_risk", "piece_notes", "slide_overlap",
    "decode_to_midi", "encode_from_midi",
    "band_profile", "band_status", "genre_band_check", "axis_feedback",
]
