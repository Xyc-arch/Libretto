#!/usr/bin/env python3
"""_audiobox_score.py — score audio files with Meta AudioBox-Aesthetics (CE/CU/PC/PQ).

RUNS UNDER THE ISOLATED VENV (.venv_audiobox, torch>=2.2), NOT the base env. Invoked by
libretto.validation.judge.AudioBoxJudge:

    <venv>/bin/python -m ... _audiobox_score.py out.json a.wav b.wav ...

Writes a JSON list aligned to the input wav order: [{"path":..,"CE":..,"CU":..,"PC":..,"PQ":..}, ...].
First call downloads the AudioBox checkpoint (needs network). CPU-only here. Scores are a learned
audio-aesthetics PROXY, confounded by the render pipeline — use for RELATIVE comparison only.
"""
import json
import sys
import warnings

warnings.filterwarnings("ignore")


def main():
    out_path, wavs = sys.argv[1], sys.argv[2:]
    if not wavs:
        json.dump([], open(out_path, "w"))
        return
    import torch

    # Force CPU: some machines have no working mps/cuda but the predictor's device probe picks mps and
    # then autocast(device_type='mps') errors. Disable the probes before init.
    torch.backends.mps.is_available = lambda: False
    torch.cuda.is_available = lambda: False

    from audiobox_aesthetics.infer import initialize_predictor

    predictor = initialize_predictor()
    rows = []
    for w in wavs:  # one at a time: robust to a single bad render; tiny CPU memory per clip
        try:
            r = predictor.forward([{"path": w}])[0]
            rows.append({"path": w, "CE": r["CE"], "CU": r["CU"], "PC": r["PC"], "PQ": r["PQ"]})
        except Exception as e:  # noqa: BLE001
            rows.append({"path": w, "error": str(e)})
    json.dump(rows, open(out_path, "w"), indent=2)
    print(f"scored {sum('error' not in r for r in rows)}/{len(rows)} -> {out_path}")


if __name__ == "__main__":
    main()
