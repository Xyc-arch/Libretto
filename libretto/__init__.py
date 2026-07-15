"""libretto — a descriptive symbolic-music fingerprint environment (frozen, versioned).

MIDI -> text "grammar" -> a 39-axis empirical-percentile fingerprint against a frozen,
genre-balanced 1523-song corpus distribution. The MEASUREMENT layer is fully deterministic and
reproducible; GENERATION is an LLM and is pluggable (see libretto.generation).

Data root resolves to the packaged `data/` dir, overridable with the LIBRETTO_DATA env var.
"""
import os
from pathlib import Path

__version__ = (Path(__file__).resolve().parent / "VERSION").read_text().strip()
# The frozen, validated environment this package pins (see FROZEN.md):
DISTRIBUTION_VERSION = "39-axis / 1523-song / genre-balanced / 2026-07-06"


def data_root() -> Path:
    """Directory holding the frozen data (corpus distribution, fps, grammar, answer key, KB)."""
    return Path(os.environ.get("LIBRETTO_DATA") or (Path(__file__).resolve().parent / "data"))
