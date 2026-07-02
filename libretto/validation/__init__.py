"""libretto.validation — external, causal validation of structural axes via dose-response.

Push one axis toward its extreme over graded doses (holding instrumentation fixed), render, and score with an
INDEPENDENT judge (default AudioBox-Aesthetics, a learned human-preference proxy). A negative within-song
correlation of the score with dose = the axis is quality-relevant (extremity makes it sound worse).

This is the toolkit for *extending* the system: register a lever for a new axis and the same machinery
validates it, telling you whether it moved the target axis cleanly (entanglement) and whether an external
model confirms it is quality-relevant.

Quick start
-----------
    from libretto.validation import lever, validate

    @lever("my_axis", push="high")            # add an axis lever (must match a metric in metrics_for)
    def push_my_axis(text, dose): ...

    res = validate(songs=["song_0047"], axes=["my_axis"])   # needs .venv_audiobox + fluidsynth
    for a in res.axes:
        print(a.axis, a.within_rho, a.delta, a.sign_p, a.validated)

Or from the shell:  ``python -m libretto.validation --help``

The four canonical axes WITHOUT a lever (emergent chord-set / SSM statistics with no isolated handle) are
documented with reasons in ``UNCOVERED`` and surfaced by ``ValidationResult.coverage()``.
"""
from .levers import LEVERS, UNCOVERED, Lever, lever, perturb, register_lever
from .judge import AudioBoxJudge, Judge
from .validate import (
    AxisResult, ValidationResult, validate, summarize, sign_test_p, canonical_axes,
    DEFAULT_SONGS, DEFAULT_DOSES,
)

__all__ = [
    "LEVERS", "UNCOVERED", "Lever", "lever", "register_lever", "perturb",
    "Judge", "AudioBoxJudge",
    "validate", "summarize", "sign_test_p", "canonical_axes",
    "AxisResult", "ValidationResult", "DEFAULT_SONGS", "DEFAULT_DOSES",
]
