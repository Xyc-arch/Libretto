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

    def _score_chunk(self, wav_paths: list[str]) -> list[dict]:
        with tempfile.TemporaryDirectory(prefix="audiobox_") as td:
            out = Path(td) / "scores.json"
            subprocess.run([str(self.python), str(SCORER), str(out), *map(str, wav_paths)], check=True)
            return json.loads(out.read_text())

    def score(self, wav_paths: list[str], workers: int | None = None) -> list[dict]:
        """Score every wav (one dict per wav, in input order). With workers>1 the wavs are split into that
        many contiguous chunks scored by concurrent AudioBox processes (default $LIBRETTO_AUDIOBOX_WORKERS
        or 1). Each worker re-loads the model, so use it when there are many clips."""
        if not wav_paths:
            return []
        if not self.available():
            raise FileNotFoundError(
                f"AudioBox interpreter not found at {self.python}. Create .venv_audiobox (see class docstring) "
                f"or pass python=/path/to/venv/bin/python (or set $LIBRETTO_AUDIOBOX_PY)."
            )
        workers = workers or int(os.environ.get("LIBRETTO_AUDIOBOX_WORKERS", 1))
        if workers <= 1 or len(wav_paths) <= workers:
            return self._score_chunk(wav_paths)
        # split into `workers` contiguous chunks, score concurrently, concatenate in order
        from concurrent.futures import ThreadPoolExecutor
        k = -(-len(wav_paths) // workers)                       # ceil chunk size
        chunks = [wav_paths[i:i + k] for i in range(0, len(wav_paths), k)]
        with ThreadPoolExecutor(max_workers=workers) as ex:
            parts = list(ex.map(self._score_chunk, chunks))
        return [d for part in parts for d in part]
