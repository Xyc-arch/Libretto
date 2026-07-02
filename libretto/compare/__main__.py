"""CLI for libretto.compare.

  python -m libretto.compare cost [SONG ...]        # encoding-cost contrast (default: whole corpus)
  python -m libretto.compare benchmark [--oracle] [--hallucination] [--out DIR]
"""
import argparse
import sys
from pathlib import Path

from libretto import data_root
from . import benchmark as B
from .cost import corpus_cost, encoding_cost


def _cmd_cost(args):
    if args.songs:
        rows = [(s, encoding_cost(s)) for s in args.songs]
        for name, c in rows:
            print(f"{Path(str(name)).stem:16} notes={c.n_notes:5} voices={c.n_voices} "
                  f"onset_recovery={c.onset_recovery:6} edit_blast={c.edit_blast:8} "
                  f"vertical_align={c.vertical_align:8} | libretto={c.libretto}")
        return
    songs = sorted((data_root() / "grammar").glob("*.txt"))
    tot, rows = corpus_cost(songs)
    print(f"corpus: {tot['n_songs']} songs, {tot['n_notes']:,} notes")
    print(f"  onset-recovery additions : ABC {tot['onset_recovery']:,}   vs Libretto {tot['libretto']}")
    print(f"  edit-blast (per 1 edit)  : ABC {tot['edit_blast']:,}   vs Libretto {tot['libretto']}")
    print(f"  vertical-alignment adds  : ABC {tot['vertical_align']:,}   vs Libretto {tot['libretto']}")


def _cmd_benchmark(args):
    items = B.build_hallucination() if args.hallucination else B.build(B.HIGH_SIGNAL)
    if args.oracle:
        ok, d = B.oracle(items)
        print(f"oracle: {d['correct']}/{d['total']} correct, {d['impossible']} impossible -> {'OK' if ok else 'FAIL'}")
        if not ok:
            sys.exit(1)
    if args.out:
        out = Path(args.out); (out / "prompts").mkdir(parents=True, exist_ok=True)
        for it in items:
            ap, lp = B.prompts(it, quick=args.hallucination)
            (out / "prompts" / f"{it['id']}_abc.txt").write_text(ap, encoding="utf-8")
            (out / "prompts" / f"{it['id']}_lib.txt").write_text(lp, encoding="utf-8")
        import json
        (out / "manifest.json").write_text(json.dumps(items, indent=2), encoding="utf-8")
        print(f"wrote {len(items)} items + {len(items)*2} prompts to {out}")
    else:
        print(f"built {len(items)} items across tasks: " +
              ", ".join(sorted({it['task'] for it in items})) + "  (use --out DIR to write prompts)")


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m libretto.compare")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("cost", help="deterministic encoding-cost contrast")
    c.add_argument("songs", nargs="*", help="grammar files (default: whole packaged corpus)")
    c.set_defaults(func=_cmd_cost)
    b = sub.add_parser("benchmark", help="tool-free reading benchmark stimuli/prompts")
    b.add_argument("--oracle", action="store_true", help="self-check that ground truth scores 100%%")
    b.add_argument("--hallucination", action="store_true", help="dense/deep quick-read set")
    b.add_argument("--out", help="write prompts + manifest to this dir")
    b.set_defaults(func=_cmd_benchmark)
    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
