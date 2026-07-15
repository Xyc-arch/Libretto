#!/usr/bin/env python3
"""_audiobox_score.py — score audio files with Meta AudioBox-Aesthetics (CE/CU/PC/PQ).

RUNS UNDER THE ISOLATED VENV (.venv_audiobox, torch>=2.2), NOT the base env. Invoked by
libretto.validation.judge.AudioBoxJudge:

    <venv>/bin/python -m ... _audiobox_score.py out.json a.wav b.wav ...

Two output modes, chosen by the out-path extension:
  * out.json  — BATCH: writes a JSON list aligned to input order, ONCE at the end (legacy; used by
                libretto.validation.judge.AudioBoxJudge).
  * out.jsonl — INCREMENTAL + RESUMABLE: appends one {"path",..} line per song, flushed+fsynced as
                each finishes. On start it reads the file and SKIPS any path already scored, so you can
                stop at any time (Ctrl-C / kill) and re-run to continue, or pre-seed it to skip songs.
First call downloads the AudioBox checkpoint (needs network). CPU-only here. Scores are a learned
audio-aesthetics PROXY, confounded by the render pipeline — use for RELATIVE comparison only.
"""
import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")


def _score_one(predictor, w):
    try:
        r = predictor.forward([{"path": w}])[0]
        return {"path": w, "CE": r["CE"], "CU": r["CU"], "PC": r["PC"], "PQ": r["PQ"]}
    except Exception as e:  # noqa: BLE001
        return {"path": w, "error": str(e)}


def _load_predictor():
    import torch

    # Force CPU: some machines have no working mps/cuda but the predictor's device probe picks mps and
    # then autocast(device_type='mps') errors. Disable the probes before init.
    torch.backends.mps.is_available = lambda: False
    torch.cuda.is_available = lambda: False
    from audiobox_aesthetics.infer import initialize_predictor

    return initialize_predictor()


def main():
    out_path, wavs = sys.argv[1], sys.argv[2:]
    incremental = out_path.endswith(".jsonl")

    if not wavs:
        if not incremental:
            json.dump([], open(out_path, "w"))
        return

    if incremental:
        # resume: skip paths already present (tolerate a torn final line from a prior kill)
        done = set()
        if os.path.exists(out_path):
            with open(out_path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        done.add(json.loads(line)["path"])
                    except Exception:  # noqa: BLE001
                        pass
        todo = [w for w in wavs if w not in done]
        print(f"incremental: {len(done)} already scored, {len(todo)} to do -> {out_path}", flush=True)
        if not todo:
            return
        predictor = _load_predictor()
        with open(out_path, "a") as fh:
            for i, w in enumerate(todo, 1):
                fh.write(json.dumps(_score_one(predictor, w)) + "\n")
                fh.flush()
                os.fsync(fh.fileno())            # persisted before the next song starts
                print(f"[{i}/{len(todo)}] {w}", flush=True)
        return

    # batch mode (legacy, aligned list, single write at the end)
    predictor = _load_predictor()
    rows = [_score_one(predictor, w) for w in wavs]  # one at a time: robust to a single bad render
    json.dump(rows, open(out_path, "w"), indent=2)
    print(f"scored {sum('error' not in r for r in rows)}/{len(rows)} -> {out_path}")


if __name__ == "__main__":
    main()
