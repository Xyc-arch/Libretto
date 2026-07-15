"""libretto.corpus.build — encode a genre-grounded song selection into staged grammar files + answer-key rows.

Consumes a selection ({genre: [source paths]}) and the grounded artist table (for MBID/evidence), encodes each
MIDI with the SAME call the original corpus used (`encode(src, "adaptive", drums-off, no-max-bars, anonymize)`)
so old and new are directly comparable, and writes to a STAGING dir + key (the frozen v2.0.0 corpus stays
untouched until a deliberate finalize/rebuild). Resumable (skips sources already staged). QC: token bounds,
skip encode failures.

Encoding is embarrassingly parallel (each MIDI->grammar is independent); with --workers>1 the CPU-heavy
encode runs in a process Pool while the MAIN process stays the single writer (assigns ids, writes grammar,
checkpoints the key) so the key file is never clobbered. Workers recycle (maxtasksperchild) to bound the
music21 memory accumulation seen in long-lived processes.

  python -m libretto.corpus.build --selection sel.json --grounded grounded.jsonl \
      --midi-root <clean_midi> --out-grammar STAGE/grammar_new --out-key STAGE/key_new.json \
      [--start-id 316] [--limit N] [--workers 8]
"""
import argparse
import json
import re
from multiprocessing import Pool
from pathlib import Path

from libretto.core import midi_to_grammar as mtg

TOKEN_LO, TOKEN_HI = 500, 15000


def _hdr(text):
    h = text.splitlines()[0] if text.strip() else ""
    def g(tag):
        m = re.search(rf"{tag}:\s*([^|]+)", h)
        return m.group(1).strip() if m else ""
    ntok = len(re.findall(r"@\d+", text))
    return dict(key=g("KEY"), meter=g("METER"), tempo=g("TEMPO"), bars=g("BARS"), tokens=ntok)


def _encode_one(job):
    """Pool worker (top-level so it's picklable under spawn). Encode one source; carry genre/src through."""
    genre, src, midi_root = job
    try:
        text = mtg.encode(Path(midi_root) / src, "adaptive", True, None, anonymize=False)
        if not text or not text.strip():                     # encode can return None/empty (no notes)
            return genre, src, None, "empty encode"
        return genre, src, text, None
    except Exception as e:  # noqa: BLE001
        return genre, src, None, str(e)[:60]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--selection", required=True)
    ap.add_argument("--grounded", required=True)
    ap.add_argument("--midi-root", required=True)
    ap.add_argument("--out-grammar", required=True)
    ap.add_argument("--out-key", required=True)
    ap.add_argument("--start-id", type=int, default=316)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=1, help="parallel encode processes (1 = serial)")
    a = ap.parse_args(argv)

    sel = json.load(open(a.selection))
    grounded = {r["artist"]: r for r in (json.loads(l) for l in open(a.grounded)) if r.get("artist")}
    outg = Path(a.out_grammar); outg.mkdir(parents=True, exist_ok=True)
    keyp = Path(a.out_key)
    key = json.loads(keyp.read_text()) if keyp.exists() else {}
    done_src = {v["source"] for v in key.values()}                      # resume
    next_id = max([int(re.search(r"\d+", k).group()) for k in key] + [a.start_id - 1]) + 1

    jobs = [(g, s, a.midi_root) for g, paths in sel.items() for s in paths if s not in done_src]
    if a.limit:
        jobs = jobs[:a.limit]
    state = {"ok": 0, "skip": 0, "next_id": next_id}

    def handle(res):
        """Single-writer collector: gate, assign id, write grammar, update key, periodic checkpoint."""
        genre, src, text, err = res
        if err is not None:
            state["skip"] += 1; print(f"  SKIP encode-fail {src}: {err}", flush=True); return
        hf = _hdr(text)
        if hf["tokens"] < TOKEN_LO or hf["tokens"] > TOKEN_HI:           # gate on note-token count (matches corpus)
            state["skip"] += 1; print(f"  SKIP token-outlier {src} ({hf['tokens']} tokens)", flush=True); return
        sid = f"song_{state['next_id']:04d}"; state["next_id"] += 1
        (outg / f"{sid}.txt").write_text(text, encoding="utf-8")
        art = src.split("/")[0]
        gr = grounded.get(art, {})
        key[sid] = dict(title=Path(src).stem, artist=art, source=src, genre=genre,
                        mbid=gr.get("mbid"), genre_evidence=gr.get("evidence"), genre_confidence=gr.get("confidence"),
                        **hf)
        state["ok"] += 1
        if state["ok"] % 25 == 0:
            keyp.write_text(json.dumps(key, indent=1, ensure_ascii=False))   # periodic checkpoint
            print(f"  ...encoded {state['ok']} (skipped {state['skip']}) [{a.workers}w]", flush=True)

    if a.workers > 1:
        # recycle workers to cap music21 memory growth; imap_unordered streams results to the single writer
        with Pool(a.workers, maxtasksperchild=15) as pool:
            for res in pool.imap_unordered(_encode_one, jobs, chunksize=1):
                handle(res)
    else:
        for job in jobs:
            handle(_encode_one(job))

    keyp.write_text(json.dumps(key, indent=1, ensure_ascii=False))
    print(f"DONE: encoded {state['ok']} new, skipped {state['skip']}. total staged key rows: {len(key)} -> {keyp}")


if __name__ == "__main__":
    main()
