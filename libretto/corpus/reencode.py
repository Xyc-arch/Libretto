"""libretto.corpus.reencode — re-encode the whole corpus grammar from source MIDI with the LIVE encoder.

Overwrites libretto/data/grammar/song_XXXX.txt from each song's source .mid (enriched settings:
adaptive grid, keep drums, no bar cap, real voice names). Parallel (--workers) and PROGRESS-AUDITABLE:
each finished song is appended to state/reencode_progress.jsonl (flushed), so you can watch live:

    wc -l libretto/corpus/state/reencode_progress.jsonl        # songs done so far
    tail libretto/corpus/state/reencode_progress.jsonl         # latest + any errors

The old grammar is preserved in git; a song that fails to encode keeps its existing file (logged).

    python -m libretto.corpus.reencode --workers 3
"""
import argparse
import json
import os
from multiprocessing import Pool
from pathlib import Path

import libretto
from libretto.core import midi_to_grammar as mtg

DATA = libretto.data_root()
# source .mid live in clean_midi/ (artist folders) = two levels above the project: DATA=.../<proj>/libretto/data
MIDI_ROOT = Path(os.environ.get("CLEAN_MIDI_ROOT", DATA.parents[2]))
GRAMMAR = DATA / "grammar"
TRUTH = DATA / "answer_key" / "grammar_truth.json"
STATE = Path(__file__).resolve().parent / "state"
PROGRESS = STATE / "reencode_progress.jsonl"


def _encode_one(job):
    """Worker: encode one source MIDI -> overwrite its grammar file. Returns a status dict.
    Writes its own distinct file (no contention). On failure the existing grammar is left untouched."""
    sid, src, out = job
    try:
        text = mtg.encode(Path(src), "adaptive", True, None, anonymize=False)
        if not text:
            return {"sid": sid, "ok": False, "err": "no pitched content"}
        Path(out).write_text(text, encoding="utf-8")
        head = text.splitlines()
        nvoices = len(head[1].split(":", 1)[1].split(",")) if len(head) > 1 else 0
        return {"sid": sid, "ok": True, "nvoices": nvoices, "tokens": len(text) // 4}
    except Exception as e:  # noqa: BLE001
        return {"sid": sid, "ok": False, "err": str(e)[:80]}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--resume", action="store_true", help="skip songs already in the progress log")
    a = ap.parse_args(argv)
    STATE.mkdir(parents=True, exist_ok=True)

    truth = json.loads(TRUTH.read_text())
    done = set()
    if a.resume and PROGRESS.exists():
        for line in PROGRESS.read_text().splitlines():
            try:
                done.add(json.loads(line)["sid"])
            except Exception:  # noqa: BLE001
                pass
    else:
        PROGRESS.write_text("")                       # fresh run: truncate the progress log

    jobs = []
    for sid, m in sorted(truth.items(), key=lambda kv: int(kv[0].split("_")[1])):
        if sid in done or not m.get("source"):
            continue
        src = MIDI_ROOT / m["source"]
        if src.exists():
            jobs.append((sid, str(src), str(GRAMMAR / f"{sid}.txt")))
    print(f"re-encoding {len(jobs)} songs with {a.workers} workers -> {GRAMMAR}", flush=True)
    print(f"watch: wc -l {PROGRESS}", flush=True)

    ok = err = 0
    with open(PROGRESS, "a") as plog, Pool(a.workers, maxtasksperchild=25) as pool:
        for i, r in enumerate(pool.imap_unordered(_encode_one, jobs, chunksize=1), 1):
            plog.write(json.dumps(r) + "\n"); plog.flush(); os.fsync(plog.fileno())
            ok += r["ok"]; err += (not r["ok"])
            if i % 50 == 0 or i == len(jobs):
                print(f"  ...{i}/{len(jobs)}  ok={ok} err={err}", flush=True)
    print(f"\nDONE: {ok} re-encoded, {err} failed (existing grammar kept). progress log: {PROGRESS}")
    if err:
        fails = [json.loads(l) for l in PROGRESS.read_text().splitlines() if not json.loads(l)["ok"]]
        print("  failures:", [(f["sid"], f.get("err")) for f in fails[:10]])


if __name__ == "__main__":
    main()
