#!/usr/bin/env python3
"""newgen_setup.py — prep for GENUINE generation (no held-out answer => no leakage possible).

Three task types, each generating material that does NOT exist in the original:
  continuation — new bars AFTER the song's final bar (what plausibly comes next)
  insertion    — a NEW section inserted between two existing sections (connects both sides)
  prefix       — a NEW intro PREPENDED before the song's first bar (flows into bar 1)

There is no ground truth (the material is invented), so success is: source-coherent + non-degenerate +
genuinely-new (note-level), NOT "matches an answer" (there is none). Reuses the validated fingerprint.

Usage: python3 newgen_setup.py <song_id> <continuation|insertion|prefix>
"""
import json, sys, re
from pathlib import Path
import numpy as np
import metric_discovery as md
from understanding_probe import Song

SCRIPT = Path(__file__).resolve().parent
GRAMMAR = SCRIPT / "grammar"
OUT = SCRIPT / "compositions" / "newgen"; OUT.mkdir(parents=True, exist_ok=True)
KEY = json.loads((SCRIPT/"answer_key"/"grammar_truth.json").read_text())
CANON = json.loads((SCRIPT/"corpus_distribution.json").read_text())
AXES = CANON["axes_order"]; COLS = {a: np.array(CANON["axes"][a]["values"], float) for a in AXES}
corpus_fp = {s: np.array(v, float) for s, v in
             json.loads((SCRIPT/"compositions"/"continuation"/"corpus_fps.json").read_text()).items()}
K = 3
BANDS = dict(COHERE_MAX=22.0,        # D(region,source) <= this => region coheres with the source's profile
             C1_MAX_EXTREMES=3,      # genre-aware extremes on the region (non-degeneracy)
             NOVELTY_MAX=0.30,       # copy_risk (note-overlap vs source) < this => genuinely new
             REGION_MIN=6, REGION_MAX=40,    # plausible section/intro/continuation length (bars)
             BOUND_PC_MIN=0.10)      # boundary pc-set Jaccard floor (shared tonal center, not a jolt)

def fp(p):
    m = md.metrics_for(Song(p), p)
    return np.array([round(float((COLS[a] <= float(m[a])).mean()*100)) for a in AXES], float)
def dist(a,b): return float(np.mean(np.abs(a-b)))

def main(sid, typ):
    assert typ in ("continuation","insertion","prefix")
    gpath = GRAMMAR/f"{sid}.txt"
    head = gpath.read_text().splitlines()[0]
    voices_line = next((l for l in gpath.read_text().splitlines() if l.startswith("VOICES:")), "VOICES:")
    voices = [v.strip() for v in voices_line.split(":",1)[1].split(",")]
    nb = int(re.search(r"BARS:\s*(\d+)", head).group(1))
    sfp = fp(gpath); prof = {a:int(sfp[i]) for i,a in enumerate(AXES)}
    d = sorted(((dist(sfp,corpus_fp[s]),s) for s in corpus_fp if s!=sid))[:K]
    cen = np.mean([corpus_fp[s] for _,s in d],axis=0)
    sal = sorted(range(len(AXES)),key=lambda i:abs(cen[i]-50),reverse=True)[:6]
    tend = ", ".join(f"{AXES[i].split('_',1)[1]}={int(cen[i])}" for i in sal)
    neighbors = [(s,round(dd,1)) for dd,s in d]
    chance = float(np.mean([dist(sfp,corpus_fp[s]) for s in corpus_fp if s!=sid]))
    nbd = float(np.mean([dd for dd,_ in d]))
    insertion_bar = round(0.55*nb) if typ=="insertion" else None

    case = dict(sid=sid, type=typ, genre=KEY[sid].get("genre") or "pop_rock_orig",
                artist=KEY[sid].get("artist"), title=KEY[sid].get("title"),
                hdr=head, source_bars=nb, voices=voices, source_fp=prof,
                neighbors=neighbors, tend=tend, insertion_bar=insertion_bar,
                ref=dict(chance=round(chance,1), neighbor=round(nbd,1)), bands=BANDS)
    (OUT/f"{sid}_{typ}_case.json").write_text(json.dumps(case,indent=2))
    print(f"=== NEWGEN SETUP — {sid} | {case['artist']} — {case['title']} | {case['genre']} | {nb} bars | task={typ} ===")
    print(f"  reference: chance(random corpus)={chance:.1f}  neighbor(k={K})={nbd:.1f}")
    print(f"  neighbors {neighbors}  | tendencies: {tend}")
    if typ=="insertion": print(f"  insertion point: after bar {insertion_bar} (connect bar {insertion_bar} -> {insertion_bar+1})")
    print(f"  targets: cohere D(region,source) <= {BANDS['COHERE_MAX']} (chance {chance:.0f}); "
          f"C1 ext <= {BANDS['C1_MAX_EXTREMES']}; novelty copy_risk < {BANDS['NOVELTY_MAX']}; region {BANDS['REGION_MIN']}-{BANDS['REGION_MAX']} bars")
    print(f"  wrote {OUT/f'{sid}_{typ}_case.json'}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
