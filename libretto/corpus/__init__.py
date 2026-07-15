"""libretto.corpus — corpus curation & calibration toolkit.

The reproducible pipeline that BUILDS the descriptive substrate (as opposed to `libretto.core`, which measures
against a frozen build):

- `genres`   — evidence-grounded artist -> genre from MusicBrainz (`ground()`, `TAXONOMY`, CLI).
- (planned)  — selection/balancing, MIDI->grammar encoding, and canonical-distribution ("statistical cloud")
               rebuild, ported from the repo-root build scripts.

Rebuilding the distribution is a DELIBERATE frozen-core change (re-maps all coordinates → MAJOR version +
re-validation); this toolkit exists to make that reproducible, not routine.
"""
# submodules imported explicitly by callers (e.g. `from libretto.corpus import genres`) — not eagerly here,
# so `python -m libretto.corpus.genres` doesn't double-import.
__all__ = ["genres"]
