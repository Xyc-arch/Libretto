#!/usr/bin/env python3
"""judge.py — pluggable external judge for axis validation.

A *judge* scores rendered audio so the validator can watch a dose-response. It is the INDEPENDENT measure:
nothing about it knows the axis system. Implement the :class:`Judge` protocol to use your own preference
model; the default :class:`AudioBoxJudge` wraps Meta AudioBox-Aesthetics.

    class Judge(Protocol):
        primary: str                                    # the metric key used for the dose-response (e.g. "CE")
        def score(self, wav_paths: list[str]) -> list[dict]:  # one dict per wav, aligned to input order

Each returned dict maps metric name -> float (and may include "error"). AudioBox returns CE (content
enjoyment, the default headline), CU, PC, PQ. Scores are a learned PROXY for human audio preference and are
confounded by the render pipeline — valid for RELATIVE comparison within one identical pipeline, never as an
absolute gate.
"""
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Protocol, runtime_checkable

SCORER = Path(__file__).resolve().parent / "_audiobox_score.py"


@runtime_checkable
class Judge(Protocol):
    primary: str
    def score(self, wav_paths: list[str]) -> list[dict]:
        ...


class AudioBoxJudge:
    """Meta AudioBox-Aesthetics, run in an isolated venv (its torch can't share the base env).

    The model lives in a separate interpreter; we shell out to a one-shot scorer that loads the model once
    and scores every wav. Point ``python`` at that venv's interpreter (default: ``$LIBRETTO_AUDIOBOX_PY`` or
    ``.venv_audiobox/bin/python`` under the current dir). Set it up once::

        python3.11 -m venv .venv_audiobox
        .venv_audiobox/bin/pip install audiobox_aesthetics==0.0.4
    """

    METRICS = ("CE", "CU", "PC", "PQ")

    def __init__(self, python: str | os.PathLike | None = None, primary: str = "CE"):
        self.primary = primary
        self.python = Path(python or os.environ.get("LIBRETTO_AUDIOBOX_PY")
                           or Path.cwd() / ".venv_audiobox" / "bin" / "python")

    def available(self) -> bool:
        return Path(self.python).exists()

    def score(self, wav_paths: list[str]) -> list[dict]:
        if not wav_paths:
            return []
        if not self.available():
            raise FileNotFoundError(
                f"AudioBox interpreter not found at {self.python}. Create .venv_audiobox (see class docstring) "
                f"or pass python=/path/to/venv/bin/python (or set $LIBRETTO_AUDIOBOX_PY)."
            )
        with tempfile.TemporaryDirectory(prefix="audiobox_") as td:
            out = Path(td) / "scores.json"
            subprocess.run([str(self.python), str(SCORER), str(out), *map(str, wav_paths)], check=True)
            return json.loads(out.read_text())
