"""libretto.tasks.newgen.retrieval_ablation — accumulating retrieval ON/OFF ablation for newgen (AXIS 1).

Reusable, compute-frugal harness: generate a few pieces whenever you have compute, score + append, and `report`
recomputes the pass rate + bootstrap SE/CI over ALL accumulated rows (per condition + genre-paired). No fixed
batch — n grows over sessions, SE shrinks.

  ON  = full newgen prompt (numeric genre bands + KB idiom concepts + real exemplars); each `seed` draws
        DIFFERENT exemplars (build_retrieval(genre, seed=s)), so repeats are genuinely distinct retrieval draws.
  OFF = the SAME prompt with the retrieval block removed (numeric bands only).

Generation is left to the caller (any Generator / agent): `prompt` writes the brief, you generate, then `add`
scores the grammar and appends. Results file: $LIBRETTO_ABLATION_OUT or ./retrieval_ablation_accum.jsonl.

CLI:  python -m libretto.tasks.newgen.retrieval_ablation {prompt GENRE SEED on|off OUTDIR | add GENRE SEED on|off GRAMMAR | report}
"""
import json
import os
import random
import sys
from pathlib import Path

from libretto.core import Song
from .newgen_measure import measure
from . import newgen_setup as NS
from . import retrieval as R

# These keys MUST match the genre_conditioned keys of the ACTIVE distribution. After the v3.0.0 corpus
# rebuild the cloud carries the new grounded taxonomy (libretto.corpus.genres.TAXONOMY); the N=8 ablation
# run uses the best-corpus-supported genres (>=~70 songs). reggae_ska / blues_gospel / latin are valid but
# thinner (~30-40 songs) — add them only if compute allows N=11. (Pre-rebuild, the frozen 314 distribution
# still uses the OLD labels: core_pop_rock, latin_reggae_world, film_score.)
GENRES = ["pop_rock", "funk_soul_rnb", "electronic_dance", "jazz",
          "folk_country", "classical", "metal", "hiphop_rap"]
_OFF_NOTE = "(NO idiom retrieval — compose from the numeric genre-band targets below alone; no KB, no exemplars.)"


def accum_path():
    return Path(os.environ.get("LIBRETTO_ABLATION_OUT", Path.cwd() / "retrieval_ablation_accum.jsonl"))


def prompts(genre, seed):
    """Return (ON, OFF) newgen prompts for (genre, seed). OFF = ON minus the injected retrieval block."""
    on, _case = NS.build_genre_prompt(genre, seed=seed)
    retr_text = R.build_retrieval(genre, seed=seed)["text"]
    return on, on.replace(retr_text, _OFF_NOTE)


def score(genre, grammar_path):
    """Measure a generated grammar against the genre target -> a result row (dict)."""
    try:
        Song(str(grammar_path)); valid = True
    except Exception:  # noqa: BLE001
        valid = False
    rep = measure(str(grammar_path), genre) if valid else {}
    return dict(genre=genre, valid=valid, pas=bool(rep.get("verdict")), copy=rep.get("copy_risk"),
                fit=rep.get("genre_fit"), c1=rep.get("c1"), c1ext=rep.get("c1_ext"), new=rep.get("new"))


def append_row(row):
    with open(accum_path(), "a") as f:
        f.write(json.dumps(row) + "\n")


def _boot(passes, n_boot=4000):
    n = len(passes)
    if not n:
        return 0.0, 0.0, (0.0, 0.0)
    p = sum(passes) / n
    rng = random.Random(0)
    bs = sorted(sum(passes[rng.randrange(n)] for _ in range(n)) / n for _ in range(n_boot))
    se = (sum((x - p) ** 2 for x in bs) / len(bs)) ** 0.5
    return p, se, (bs[int(0.025 * len(bs))], bs[int(0.975 * len(bs))])


def report(rows=None):
    """Aggregate accumulated rows: per-condition pass ± bootstrap SE/CI, genre-paired diff, per-genre breakdown."""
    if rows is None:
        ap = accum_path()
        rows = [json.loads(x) for x in ap.read_text().splitlines()] if ap.exists() else []
    out = {"n": len(rows), "valid": sum(r["valid"] for r in rows)}
    for cond in ("on", "off"):
        rc = [r for r in rows if r["cond"] == cond]
        p, se, ci = _boot([1 if r["pas"] else 0 for r in rc])
        out[cond] = dict(k=sum(1 for r in rc if r["pas"]), n=len(rc), p=p, se=se, ci95=list(ci))
    by = {}
    for r in rows:
        by.setdefault((r["genre"], r["seed"]), {})[r["cond"]] = r["pas"]
    pairs = [v for v in by.values() if "on" in v and "off" in v]
    if pairs:
        diff = [(1 if v["on"] else 0) - (1 if v["off"] else 0) for v in pairs]
        out["paired"] = dict(n=len(pairs), mean_on_minus_off=sum(diff) / len(diff),
                             on_only=sum(1 for d in diff if d > 0), off_only=sum(1 for d in diff if d < 0))
    return out


# ---------------------------------------------------------------- CLI
def _cmd_prompt(genre, seed, cond, outdir):
    on, off = prompts(genre, int(seed))
    out = Path(outdir); out.mkdir(parents=True, exist_ok=True)
    p = out / f"{genre}__s{seed}__{cond}.txt"
    p.write_text(on if cond == "on" else off, encoding="utf-8")
    print(p)


def _cmd_add(genre, seed, cond, grammar):
    row = score(genre, grammar); row["seed"] = int(seed); row["cond"] = cond
    append_row(row); print(json.dumps(row))


def _cmd_report():
    r = report()
    print(f"accumulated: {r['n']} pieces ({r['valid']} valid) -> {accum_path()}")
    for c in ("on", "off"):
        d = r[c]
        print(f"  {c.upper():3}: pass {d['k']}/{d['n']} = {d['p']:.2f} ± {d['se']:.2f}  95%CI [{d['ci95'][0]:.2f},{d['ci95'][1]:.2f}]")
    if "paired" in r:
        pr = r["paired"]
        print(f"  paired (n={pr['n']}): mean(ON-OFF) = {pr['mean_on_minus_off']:+.2f}  "
              f"(ON-only {pr['on_only']}, OFF-only {pr['off_only']})")


def main(argv=None):
    a = argv or sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    cmd = a[0]
    if cmd == "prompt":
        _cmd_prompt(a[1], a[2], a[3], a[4])
    elif cmd == "add":
        _cmd_add(a[1], a[2], a[3], a[4])
    elif cmd == "report":
        _cmd_report()
    else:
        sys.exit(f"unknown cmd {cmd!r}; use prompt|add|report")


if __name__ == "__main__":
    main()
