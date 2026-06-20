#!/usr/bin/env python3
"""Tests for the grounded gaptask diagnostic engine: bar-level C1 attribution, note-level copy localization,
and the leakage boundary (no held-out read unless real_path is passed)."""
import json
from pathlib import Path

import libretto
from libretto.core.copy_risk import GRAMMAR
from libretto.tasks.gaptask import diagnose as dg

DATA = libretto.data_root()


def test_diagnose_structure_and_leakage(tmp_path):
    # a real corpus song is a guaranteed-computable region (synthetic toy regions can be too thin for the
    # full fingerprint); we exercise structure + the leakage boundary, not a specific verdict.
    region = GRAMMAR / "song_0001.txt"
    ctx = GRAMMAR / "song_0002.txt"
    f = dg.diagnose(region, ctx, genre="jazz", target_bars=f_bars(region), neighbor_ids=None)
    assert "failed" in f and isinstance(f["failed"], list) and "bars" in f
    # no real_path -> replication block stays None (leakage boundary holds)
    assert f["replication"] is None
    # any C1 finding must carry a musical name, a direction, and a scope tag
    for a, info in (f["c1"] or {}).items():
        assert info["musical_name"] and info["direction"] in ("increase", "decrease")
        assert info["scope"] in ("localized", "global_deficit")


def f_bars(path):
    from libretto.core import Song
    return len({e["bar"] for e in Song(path).events})


def test_copy_localizes_to_a_real_song(tmp_path):
    """A region that IS a real corpus song must localize copy to that song with matched notes by bar."""
    song = GRAMMAR / "song_0001.txt"
    det = dg.localize_copy(song, source_id="song_0001")
    assert det and det["source"] == "song_0001"
    assert det["overlap"] > 0.9 and det["bars"]               # self-overlap is ~total
    assert all("notes" in b and b["n"] >= 1 for b in det["bars"])


def test_replication_block_opt_in(tmp_path):
    region = GRAMMAR / "song_0001.txt"
    ctx = GRAMMAR / "song_0002.txt"
    f = dg.diagnose(region, ctx, genre="jazz", target_bars=f_bars(region), real_path=region)
    # with real_path the block exists; region vs itself -> full overlap -> flag fires
    assert f["replication"] is not None and f["replication"]["flag"] is True
    assert f["replication"]["overlap_slid"] > 0.9


if __name__ == "__main__":
    import tempfile, pathlib
    d = pathlib.Path(tempfile.mkdtemp())
    test_diagnose_structure_and_leakage(d)
    test_copy_localizes_to_a_real_song(d)
    test_replication_block_opt_in(d)
    print("all diagnose tests passed")
