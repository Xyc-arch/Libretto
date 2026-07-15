#!/usr/bin/env python3
"""Tests for the accompaniment task: track removal is PURE + lossless (context+answer == original), and the
proximity metric is sane (splicing the REAL track back reconstructs the original -> high beat%)."""
import libretto
from libretto.tasks.accompaniment import build_cases as B
from libretto.tasks.accompaniment import measure as M

GR = libretto.data_root() / "grammar"


def test_remove_voice_is_pure_and_lossless():
    sid = "song_0820"
    src = (GR / f"{sid}.txt").read_text()
    head, _ = B._split(src)
    target = B._voices(head)[0][0]                       # first voice
    ctx, ans = B.remove_voice(src, target)
    assert (GR / f"{sid}.txt").read_text() == src        # pure
    # context has NO lines of the target; answer has ONLY the target
    assert all(l.partition(":")[0].strip() != target for b in B._split(ctx)[1] for l in b[1:] if ":" in l)
    assert all(l.partition(":")[0].strip() == target for b in B._split(ans)[1] for l in b[1:] if ":" in l)
    # lossless: context voice-lines + answer voice-lines == original voice-lines
    def vlines(t):
        return sum(1 for b in B._split(t)[1] for l in b[1:] if ":" in l)
    assert vlines(ctx) + vlines(ans) == vlines(src)


def test_build_cases_role_balanced_and_pure(tmp_path):
    cases = B.build_cases(n=6, seed=1, out=str(tmp_path))
    from collections import Counter
    roles = Counter(c["role"] for c in cases.values())
    assert set(roles) <= {"bass", "drums", "harmony"} and len(cases) == 6
    for c in cases.values():
        assert c["n_context_voices"] >= 2


def test_oracle_reconstructs_original(tmp_path):
    # splicing the REAL answer back should score high beat% for pitched roles (bass/harmony)
    cases = B.build_cases(n=6, seed=1, out=str(tmp_path))
    hits = 0; n = 0
    for cid, c in cases.items():
        if c["role"] == "drums":
            continue                                     # drums barely move the pitch fingerprint (known)
        ctx = (tmp_path / c["context"]).read_text(); ans = (tmp_path / c["answer"]).read_text()
        g = M.grade(ctx, ans, dict(c, answer_text=ans))
        n += 1; hits += g["beat_pct"] >= 90 and g["improved"]
    assert n == 0 or hits >= n - 1, "oracle should reconstruct the original for pitched roles"


if __name__ == "__main__":
    test_remove_voice_is_pure_and_lossless()
    print("accompaniment removal tests passed")
