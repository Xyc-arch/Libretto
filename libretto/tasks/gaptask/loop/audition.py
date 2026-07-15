#!/usr/bin/env python3
"""audition — pkg-native, reproducible re-pick + render for a gaptask batch.

Re-scores each case's saved refine rounds (NO agent / no Opus — pure metrics), re-picks the best under the
conditioned reprise gate (copy-passing first, then structural score), and renders ONLY the copy-passing fills
+ their held-out real region to genre-labelled MP3s for A/B listening. Deterministic given the saved rounds.

    python -m libretto.tasks.gaptask.loop.audition \
        --cases paper_data/gaptask_v3/cases --state gaptask_loop/state --listen gaptask_loop/listen

Env overrides (match the loop): GAPTASK_CASES / GAPTASK_STATE / GAPTASK_LISTEN. Rendering needs `fluidsynth`
and `lame` on PATH + a soundfont (SOUNDFONT env, or a common default); without them the re-pick + index still
run and MP3s are simply skipped.
"""
import argparse
import json
import os
import re
import subprocess
from pathlib import Path

from libretto.tasks.gaptask.refine_loop import region_fitness
from libretto.core import grammar_to_midi as _G

_BAR = re.compile(r"^@(\d+)")   # a BAR marker starts a line with @N (note-internal @slot is mid-line)
_SF_DEFAULTS = ["/Users/yichen_xu/anaconda3/lib/python3.11/site-packages/pretty_midi/TimGM6mb.sf2",
                "/Applications/MuseScore 4.app/Contents/Resources/sound/MS Basic.sf3"]


def _soundfont():
    sf = os.environ.get("SOUNDFONT")
    if sf and Path(sf).exists():
        return sf
    return next((s for s in _SF_DEFAULTS if Path(s).exists()), None)


def rebase(text):
    """Continuation regions keep the song's ABSOLUTE bar numbering (e.g. @85..@112); the decoder places bar 85
    at absolute time -> minutes of leading silence -> an unplayable MP3. Shift every line-leading @N so the
    region starts at @1. Offset-invariant for the metrics; only rendering needs this."""
    bars = [int(m.group(1)) for ln in text.splitlines() if (m := _BAR.match(ln))]
    if not bars or min(bars) == 1:
        return text
    shift = min(bars) - 1
    return "\n".join(_BAR.sub(lambda m: f"@{int(m.group(1)) - shift}", ln) if _BAR.match(ln) else ln
                     for ln in text.splitlines())


def render(txt, out, sf):
    """grammar -> .mid (rebased) -> .wav (fluidsynth) -> .mp3 (lame). Returns True on success, False if a tool
    or the soundfont is missing / decode fails (so the batch degrades gracefully to a metrics-only audition)."""
    if not sf:
        return False
    out = Path(out); mid = out.with_suffix(".mid"); wav = out.with_suffix(".wav")
    try:
        src = rebase(Path(txt).read_text())
        tmp = out.with_suffix(".grammar.txt"); tmp.write_text(src)
        _G.decode(str(tmp), str(mid)); tmp.unlink(missing_ok=True)
        subprocess.run(["fluidsynth", "-ni", "-g", "0.9", "-r", "44100", "-F", str(wav), sf, str(mid)],
                       check=True, capture_output=True)
        subprocess.run(["lame", "--quiet", "-V3", str(wav), str(out)], check=True, capture_output=True)
        wav.unlink(missing_ok=True); mid.unlink(missing_ok=True); return True
    except Exception:  # noqa: BLE001
        return False


def audition(cases_dir, state_dir, listen_dir):
    """Re-pick + render a gaptask batch. Returns the index dict. Saves ONLY copy-passing fills, genre-labelled
    `<genre>__<case>__gen/real.mp3`, and writes listen_dir/index.json."""
    cases_dir, state_dir = Path(cases_dir), Path(state_dir)
    listen_dir = Path(listen_dir); listen_dir.mkdir(parents=True, exist_ok=True)
    sf = _soundfont()
    cases = json.loads((cases_dir / "cases.json").read_text())
    for old in list(listen_dir.glob("*.mp3")) + list(listen_dir.glob("*.mid")):
        old.unlink(missing_ok=True)                     # fresh dir — only copy-passing fills are saved
    rows, n_gen, n_real, n_pass, n_flag = [], 0, 0, 0, 0
    for cid, case in cases.items():
        wd = state_dir / cid
        rounds = sorted(wd.glob("r*.txt"))
        if not rounds:
            continue
        genre = case["genre"]; nbr = [s for s, _ in case["neighbors"]]
        scored = []
        for r in rounds:
            try:
                f = region_fitness(str(r), str(cases_dir / case["ctx"]), genre=genre,
                                   target_bars=case["target_bars"], neighbor_ids=nbr, region_type=case["type"])
                scored.append((0 if f.get("copy_pass") else 1, f["score"], f["copy_risk"], r))
            except Exception:  # noqa: BLE001
                pass
        if not scored:
            continue
        scored.sort()
        gate, sc, cr, best = scored[0]
        (wd / "best.txt").write_text(best.read_text())
        passed = (gate == 0)
        if not passed:
            n_flag += 1
            print(f"[{cid}] {genre}: FLAGGED reprise={cr:.3f} — skipped (over the conditioned gate, not saved)",
                  flush=True)
        else:
            n_pass += 1
            stem = f"{genre}__{cid}"
            if render(wd / "best.txt", listen_dir / f"{stem}__gen.mp3", sf):
                n_gen += 1
            real = cases_dir / case["real"]
            if real.exists() and render(real, listen_dir / f"{stem}__real.mp3", sf):
                n_real += 1
            print(f"[{cid}] {genre}: saved (reprise={cr:.3f}) -> {stem}__gen/real.mp3", flush=True)
        rows.append(dict(case=cid, genre=genre, gap_type=case["type"], copy_pass=passed,
                         copy_risk=round(cr, 3), fitness=sc,
                         gen_mp3=(f"{genre}__{cid}__gen.mp3" if passed else None)))
    index = {"n_cases": len(rows), "saved_copy_pass": n_pass, "flagged_not_saved": n_flag,
             "rendered_gen": n_gen, "rendered_real": n_real, "soundfont": sf, "rows": rows}
    (listen_dir / "index.json").write_text(json.dumps(index, indent=2))
    tail = "" if sf else "  (no soundfont/renderer — metrics-only, no MP3s)"
    print(f"\nDONE: saved {n_gen} gen + {n_real} real MP3s (copy-PASSING only, genre-labelled) -> {listen_dir}  "
          f"| {n_pass}/{len(rows)} passed, {n_flag} flagged{tail}")
    return index


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cases", default=os.environ.get("GAPTASK_CASES") or "paper_data/gaptask_v3/cases")
    ap.add_argument("--state", default=os.environ.get("GAPTASK_STATE") or "gaptask_loop/state")
    ap.add_argument("--listen", default=os.environ.get("GAPTASK_LISTEN") or "gaptask_loop/listen")
    a = ap.parse_args()
    audition(a.cases, a.state, a.listen)


if __name__ == "__main__":
    main()
