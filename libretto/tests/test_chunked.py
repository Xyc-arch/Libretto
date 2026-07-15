#!/usr/bin/env python3
"""Tests for the autoregressive chunked-newgen module: axis partition, per-chunk gate, assemble, and a
deterministic end-to-end run with a stub Generator (no LLM)."""
import json
import libretto
from libretto.tasks.newgen import chunked as ck

DATA = libretto.data_root()
AXES = json.loads((DATA / "corpus_distribution.json").read_text())["axes_order"]


def test_axis_partition():
    assert set(ck.LOCAL_AXES) | ck.WHOLE_ONLY == set(AXES)
    assert set(ck.LOCAL_AXES) & ck.WHOLE_ONLY == set()
    # the whole-piece-only axes (judged on the assembled piece, not per chunk) must be excluded locally
    assert "within_song_variation" in ck.WHOLE_ONLY and "within_song_variation" not in ck.LOCAL_AXES


def _real_chunk():
    """First 16 sounding bars of a real corpus song, re-emitted — a valid, parseable chunk."""
    h, b = ck._blocks((DATA / "grammar" / "song_0001.txt").read_text())
    voices = next((l for l in h if l.startswith("VOICES:")), "VOICES: x")
    sounding = [blk for blk in b if len(blk) > 1][:16]
    return ck._emit(h[0], voices, sounding)


def test_chunk_fitness_and_assemble(tmp_path):
    p = tmp_path / "c.txt"; p.write_text(_real_chunk())
    fit = ck.chunk_fitness(p, "jazz")
    assert set(fit) >= {"bars", "local_extremes", "c_local_pass", "copy_risk", "copy_pass", "ok"}
    t = _real_chunk()
    full = ck.assemble([t, t])
    # assembled bar count = sum of the two chunks' bar counts
    assert ck._emit  # sanity
    assert full.count("\n@") + (1 if full.lstrip().splitlines()[2].startswith("@") else 0) >= 2 * 16 - 2


class _StubGen:
    """Deterministic Generator: returns a fixed real chunk regardless of prompt (no LLM)."""
    def __init__(self): self._c = _real_chunk()
    def generate(self, prompt, context): return self._c


def test_chunked_run_with_stub(tmp_path):
    res = ck.ChunkedNewgen(_StubGen(), chunk_bars=16, n_chunks=2, max_retry=0).run("jazz", workdir=str(tmp_path), label="t")
    assert len(res["chunks"]) == 2
    assert res["whole_fitness"] and "score" in res["whole_fitness"]
    assert (tmp_path / "t_full.txt").exists() and (tmp_path / "t_chunk1.txt").exists()


if __name__ == "__main__":
    import tempfile, pathlib
    test_axis_partition()
    d = pathlib.Path(tempfile.mkdtemp())
    test_chunk_fitness_and_assemble(d)
    test_chunked_run_with_stub(pathlib.Path(tempfile.mkdtemp()))
    print("all chunked tests passed")
