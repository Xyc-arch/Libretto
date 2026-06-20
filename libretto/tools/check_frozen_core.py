#!/usr/bin/env python3
"""check_frozen_core.py — enforce that the VALIDATED CORE is frozen (not just documented).

The "frozen core" = the distribution + retained axis set + encoder/decoder + metric definitions. Its
sha256 manifest is recorded in libretto/FROZEN_CORE.sha256 at each MAJOR validation. Any change to these
files without a new MAJOR version (and a deliberate re-record) is a frozen-core violation and must FAIL
a commit/merge. Tooling (tasks, CLI, generators, KB, docs) is NOT in this set and may evolve freely.

  python3 libretto/tools/check_frozen_core.py            # verify live == recorded; exit 1 on drift
  python3 libretto/tools/check_frozen_core.py --record    # re-record (ONLY for a deliberate v2.0.0 re-validation)

Run from the repo root (the paths below are repo-root-relative).
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent          # repo root (parent of libretto/)
MANIFEST = Path(__file__).resolve().parent.parent / "FROZEN_CORE.sha256"

# The validated core — distribution + axis set (inside the json) + encoder + decoder + metric defs + 29th axis.
FROZEN = [
    "libretto/data/corpus_distribution_314.json",   # distribution + axes_order (the axis SET)
    "libretto/core/midi_to_grammar.py",             # encoder
    "libretto/core/grammar_to_midi.py",             # decoder
    "libretto/core/metric_discovery.py",            # metric definitions
    "libretto/core/within_song_variation.py",       # the 29th axis definition
]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def live() -> dict:
    out = {}
    for rel in FROZEN:
        p = ROOT / rel
        if not p.exists():
            print(f"  MISSING frozen-core file: {rel}", file=sys.stderr)
            sys.exit(2)
        out[rel] = sha(p)
    return out


def main():
    cur = live()
    if "--record" in sys.argv:
        ver = (Path(__file__).resolve().parent.parent / "VERSION").read_text().strip()
        MANIFEST.write_text(json.dumps({"version": ver, "files": cur}, indent=2) + "\n")
        print(f"recorded frozen-core manifest for v{ver} ({len(cur)} files)")
        return
    if not MANIFEST.exists():
        print("  no FROZEN_CORE.sha256 — run --record once to establish the baseline", file=sys.stderr)
        sys.exit(1)
    rec = json.loads(MANIFEST.read_text())
    drift = [rel for rel in FROZEN if rec["files"].get(rel) != cur[rel]]
    if drift:
        print("  FROZEN-CORE VIOLATION — these validated-core files changed:", file=sys.stderr)
        for rel in drift:
            print(f"    - {rel}", file=sys.stderr)
        print(f"  Recorded for v{rec['version']}. A core change requires a NEW MAJOR version (v2.0.0),"
              " re-running the full validation suite, a FROZEN.md note, and `--record`.", file=sys.stderr)
        sys.exit(1)
    print(f"frozen core intact (matches recorded v{rec['version']}, {len(FROZEN)} files)")


if __name__ == "__main__":
    main()
