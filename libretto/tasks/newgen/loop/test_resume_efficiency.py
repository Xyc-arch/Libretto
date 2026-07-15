#!/usr/bin/env python3
"""Token-free regression tests for the newgen_loop control flow (mocks the model — no claude -p).

Drives the real batch._run_one to assert:
  1. RESUME reuses an on-disk draft instead of recomposing it, and a warm round resumes the session
     sending only the feedback (>=10x smaller input than a cold revise).
  2. GOOD-ENOUGH early-stop: an on-target draft with <= good_ext extremes stops the loop (no more calls).
  3. PATIENCE early-stop: a revise round that fails to beat the incumbent stops the loop.

Does NOT verify that `claude -p --resume` retains context server-side — that needs one real run.
Run: python newgen_loop/test_resume_efficiency.py
"""
import sys, tempfile, shutil
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))   # repo root
import libretto.tasks.newgen.loop.batch as B


def _fakegen(calls):
    class FakeGen:
        def start(self, prompt, context=None):
            calls.append(("start", len(prompt)))
            return {"text": "KEY: C | G\nVOICES: P[prog=0]\n@1 C4@1>1", "session": "s1",
                    "dir": "/tmp/nx", "out": "/tmp/nx/c.txt"}
        def resume(self, handle, message):
            calls.append(("resume", len(message)))
            return {"text": "KEY: C | G2\nVOICES: P[prog=0]\n@1 E4@1>1", "session": handle["session"],
                    "dir": handle["dir"], "out": handle["out"]}
        def cleanup(self, handle):
            pass
    return FakeGen()


def _mock_feedback(ext_seq, is_target=True):
    """Each scored round returns the next (n_extreme, is_target) from the sequence."""
    it = iter(ext_seq)
    def fb(path, genre):
        n = next(it)
        tgt = is_target if isinstance(is_target, bool) else next(is_target)
        return ([f"fix (ext {n})"], n <= 2, dict(reads_as=f"{genre} {'ok' if tgt else 'wrong'}",
                                                  is_target=tgt, n_extreme=n, copy_risk=0.2))
    return fb


def _scratch():
    d = Path(tempfile.mkdtemp(prefix="ng_test_")); B.STATE = d; return d


def test_resume_and_warm():
    d = _scratch(); calls = []
    B.compose_feedback = _mock_feedback([8, 6, 4])          # disk r1=8, then improves each round
    wd = d / "jazz" / "seed_0"; wd.mkdir(parents=True)
    (wd / "c_r1.txt").write_text("KEY: C | DISK-R1\nVOICES: P[prog=0]\n@1 G4@1>1")
    before = (wd / "c_r1.txt").read_text()
    B._run_one(("jazz", 0, {"exemplar_ids": ["x"], "text": "EX " * 300}), _fakegen(calls),
               rounds=3, target_bars=75, good_ext=3, patience=1)
    assert [c[0] for c in calls] == ["start", "resume"], f"control flow: {calls}"
    assert (wd / "c_r1.txt").read_text() == before, "disk r1 was recomposed!"
    cold, warm = calls[0][1], calls[1][1]
    assert cold / warm >= 10, f"warm not smaller: {cold} vs {warm}"
    shutil.rmtree(d, ignore_errors=True)
    print(f"OK resume+warm: r1 reused, 2 calls for 3 rounds, warm input {cold/warm:.0f}x smaller")


def test_good_enough_stop():
    d = _scratch(); calls = []
    B.compose_feedback = _mock_feedback([2])               # r1 already on-target, 2 extremes
    B._run_one(("jazz", 0, {"exemplar_ids": ["x"], "text": "EX"}), _fakegen(calls),
               rounds=3, target_bars=75, good_ext=3, patience=1)
    assert len(calls) == 1, f"good-enough should stop after r1, got {calls}"
    shutil.rmtree(d, ignore_errors=True)
    print("OK good-enough: on-target ≤good_ext stops after round 1 (1 call, not 3)")


def test_patience_stop():
    d = _scratch(); calls = []
    B.compose_feedback = _mock_feedback([10, 10, 5], is_target=False)  # r2 doesn't beat r1 -> stop
    B._run_one(("jazz", 0, {"exemplar_ids": ["x"], "text": "EX"}), _fakegen(calls),
               rounds=3, target_bars=75, good_ext=3, patience=1)
    assert len(calls) == 2, f"patience=1 should stop after the non-improving r2, got {calls}"
    shutil.rmtree(d, ignore_errors=True)
    print("OK patience: a non-improving revise stops the loop (2 calls, not 3)")


def main():
    test_resume_and_warm()
    test_good_enough_stop()
    test_patience_stop()
    print("all control-flow tests passed")


if __name__ == "__main__":
    main()
