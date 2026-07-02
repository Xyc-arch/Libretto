#!/usr/bin/env python3
"""CLI for libretto.validation.

    python -m libretto.validation                          # all registered levers, 8 songs, AudioBox
    python -m libretto.validation song_0047 song_0009      # choose seed songs
    python -m libretto.validation --axes mel_voice_range,tex_voice_count
    python -m libretto.validation --full                   # score the entire render (slow)
    python -m libretto.validation --coverage               # just print axis coverage (no run)
    python -m libretto.validation --out results.csv        # also write the per-(song,axis,dose) CSV
"""
import argparse
import sys

from .levers import LEVERS, UNCOVERED
from .validate import canonical_axes, validate, CLIP_SECONDS


def _coverage_text():
    canon = canonical_axes()
    levered = [a for a in canon if a in LEVERS]
    uncov = {a: UNCOVERED.get(a, "(no reason recorded)") for a in canon if a not in LEVERS}
    extra = [a for a in LEVERS if a not in canon]
    out = [f"Coverage: {len(levered)}/{len(canon)} canonical axes have a lever."]
    if uncov:
        out.append(f"\nNo lever ({len(uncov)}) — emergent, no isolated handle:")
        for a, r in uncov.items():
            out.append(f"  • {a}\n      {r}")
    if extra:
        out.append(f"\nNon-canonical levers registered ({len(extra)}): {', '.join(extra)}")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m libretto.validation", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("songs", nargs="*", help="seed song ids (default: 8 genre-spread)")
    ap.add_argument("--axes", help="comma-separated axis names (default: all registered levers)")
    ap.add_argument("--clip", type=int, default=CLIP_SECONDS, help="scored-window seconds (default 40)")
    ap.add_argument("--full", action="store_true", help="score the entire render (overrides --clip)")
    ap.add_argument("--coverage", action="store_true", help="print axis coverage and exit (no run)")
    ap.add_argument("--out", help="write the per-(song,axis,dose) CSV here")
    args = ap.parse_args(argv)

    if args.coverage:
        print(_coverage_text())
        return 0

    axes = args.axes.split(",") if args.axes else None
    res = validate(songs=args.songs or None, axes=axes,
                   clip_seconds=(None if args.full else args.clip))

    print(f"\n{res.n_validated}/{len(res.axes)} axes validated  "
          f"(judge primary = {res.primary}, {len(res.songs)} songs)\n")
    print(f"{'axis':28} {'push':5} {'within_ρ':>9} {'ΔCE':>7} {'sign p':>8} {'neg/n':>6} {'entangl':>8}  valid")
    print("-" * 92)
    for a in res.axes:
        print(f"{a.axis:28} {a.push:5} {a.within_rho:+9.2f} {a.delta:+7.2f} {a.sign_p:8.3f} "
              f"{a.n_neg:>2}/{a.n:<3} {a.entangled:8.1f}  {'✓' if a.validated else ''}")
    cov = res.coverage()
    print(f"\nCoverage: {cov['levered']}/{cov['canonical']} canonical axes levered; "
          f"{len(cov['uncovered'])} uncovered (run --coverage for reasons).")
    if args.out:
        res.write_csv(args.out)
        print(f"per-(song,axis,dose) CSV -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
