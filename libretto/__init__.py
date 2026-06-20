"""libretto — a descriptive symbolic-music fingerprint environment (frozen, versioned).

MIDI -> text "grammar" -> a 29-axis empirical-percentile fingerprint against a frozen
314-song corpus distribution. The MEASUREMENT layer is fully deterministic and reproducible;
GENERATION is an LLM and is pluggable (see libretto.generation).

Data root resolves to the packaged `data/` dir, overridable with the LIBRETTO_DATA env var.
"""
import os
from pathlib import Path

__version__ = (Path(__file__).resolve().parent / "VERSION").read_text().strip()
# The frozen, validated environment this package pins (see FROZEN.md):
DISTRIBUTION_VERSION = "29-axis / 314-song / 2026-06-13"


def data_root() -> Path:
    """Directory holding the frozen data (corpus distribution, fps, grammar, answer key, KB)."""
    return Path(os.environ.get("LIBRETTO_DATA") or (Path(__file__).resolve().parent / "data"))
