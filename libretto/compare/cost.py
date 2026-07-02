"""libretto.compare.cost — deterministic encoding-cost contrast: relative-duration (ABC-style) vs absolute-slot
(Libretto). Model-free; read straight off a parsed Song's note structure — no ABC export, no LLM.

Three costs, each a property of relative-vs-absolute onset encoding:

  onset_recovery  Σ over (voice, bar) of (notes − 1)   — running within-bar prefix-sum additions needed to label
                                                          every note with its beat position.
  edit_blast      Σ over voice of N(N−1)/2             — downstream onsets re-derived when a single duration edit
                                                          shifts the rest of that voice (pure relative timing).
  vertical_align  Σ_bar Σ_{event-beat q} Σ_voice (#notes in that voice before q)
                                                        — additions to align voices, i.e. to answer "what sounds
                                                          together" (the prerequisite for any harmony reasoning).

Libretto's onset is an absolute slot, so all three are 0 — hence `EncodingCost.libretto == 0`.
"""
import os
from collections import defaultdict
from dataclasses import asdict, dataclass

from libretto.core import Song


@dataclass
class EncodingCost:
    """Per-piece encoding cost. The three ABC-style costs vs Libretto's absolute-slot cost (0)."""
    n_notes: int
    n_voices: int
    n_bars: int
    onset_recovery: int          # ABC-style (relative): additions to recover every note's beat
    edit_blast: int              # ABC-style: onsets re-derived per single duration edit
    vertical_align: int          # ABC-style: additions to align voices at each event beat
    libretto: int = 0            # absolute slot -> all three are 0 by construction

    def as_dict(self):
        return asdict(self)


def _events(song):
    if isinstance(song, Song):
        return song.events
    if isinstance(song, (str, bytes, os.PathLike)):
        return Song(str(song)).events
    return list(song)                       # already an iterable of event dicts


def encoding_cost(song) -> EncodingCost:
    """Compute the encoding-cost contrast for one piece (a Song, a grammar-file path, or an event iterable)."""
    ev = _events(song)
    by_vb = defaultdict(list)                                  # (voice, bar) -> [onset-in-bar]
    by_bar_voice = defaultdict(lambda: defaultdict(list))      # bar -> voice -> [onset-in-bar]
    by_voice = defaultdict(int)
    voices, bars = set(), set()
    for e in ev:
        by_vb[(e["voice"], e["bar"])].append(e["onb"])
        by_bar_voice[e["bar"]][e["voice"]].append(e["onb"])
        by_voice[e["voice"]] += 1
        voices.add(e["voice"]); bars.add(e["bar"])

    onset_recovery = sum(len(v) - 1 for v in by_vb.values() if v)     # running prefix-sum per (voice, bar)
    edit_blast = sum(n * (n - 1) // 2 for n in by_voice.values())     # one edit shifts the voice's whole tail
    align = 0
    for vmap in by_bar_voice.values():
        qbeats = sorted({o for ons in vmap.values() for o in ons})    # beats where something happens in the bar
        for ons in vmap.values():
            s = sorted(ons)
            for q in qbeats:
                align += sum(1 for o in s if o < q)                   # notes of this voice before beat q
    return EncodingCost(len(ev), len(voices), len(bars), onset_recovery, edit_blast, align)


def corpus_cost(songs):
    """Aggregate `encoding_cost` over an iterable of Song|path|events.

    Returns (totals: dict, rows: list[EncodingCost]). Pieces that fail to parse are skipped.
    """
    rows = []
    for s in songs:
        try:
            rows.append(encoding_cost(s))
        except Exception:  # noqa: BLE001 — skip unparseable pieces, keep aggregating
            continue
    tot = dict(n_songs=len(rows),
               n_notes=sum(r.n_notes for r in rows),
               onset_recovery=sum(r.onset_recovery for r in rows),
               edit_blast=sum(r.edit_blast for r in rows),
               vertical_align=sum(r.vertical_align for r in rows),
               libretto=0)
    return tot, rows
