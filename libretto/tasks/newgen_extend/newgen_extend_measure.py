#!/usr/bin/env python3
"""newgen_measure.py — score a GENUINELY-generated region (no held-out answer).

Verdict = COHERES (region fingerprints like the source) + NON-DEGENERATE (genre-aware C1) +
GENUINELY-NEW (note-level copy_risk vs the source is only idiom-floor, not parroted) +
BOUNDARY-OK (connects to the adjacent existing material, not a hard jolt).

  python3 newgen_measure.py <sid> <type> <region.txt>
"""
import json, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
import pattern_catalog as pc
import metric_discovery as md
from understanding_probe import Song
import copy_risk as cr

SCRIPT = Path(__file__).resolve().parent
GRAMMAR = SCRIPT / "grammar"
OUT = SCRIPT / "compositions" / "newgen"
CANON = json.loads((SCRIPT/"corpus_distribution_314.json").read_text())
AXES = CANON["axes_order"]; COLS = {a: np.array(CANON["axes"][a]["values"], float) for a in AXES}
GC = CANON["genre_conditioned"]
# Length-artifact axes: dominated by how SHORT a region is, not by degeneracy. A short (8-24 bar) region
# trivially has all-distinct bars (distinct_bar_frac->100), few sections, low density variability, etc.
# The gap-task already documented that short generated regions hit these length-driven extremes. They are
# excluded from the region's degeneracy count and from the coherence distance (which is measured on the
# length-stable STYLE axes: rhythm/harmony/melody/texture).
LENGTH_AXES = {"form_distinct_bar_frac", "form_section_per100bars", "form_novelty_rate",
               "form_self_similarity", "rhy_density_variability"}
STYLE_AXES = [a for a in AXES if a not in LENGTH_AXES]

def fp_vec(p):
    m = md.metrics_for(Song(p), p)
    return np.array([round(float((COLS[a] <= float(m[a])).mean()*100)) for a in AXES], float), m
def dist(a,b): return float(np.mean(np.abs(a-b)))
def dist_style(rfp, sfp):
    idx=[i for i,a in enumerate(AXES) if a in STYLE_AXES]
    return float(np.mean(np.abs(rfp[idx]-sfp[idx])))
def ga_extremes(prof, m, genre, src_prof=None):
    """Degeneracy = extremes the REGION introduces. Excludes: length-artifact axes (shortness, not
    degeneracy); genre-band-idiomatic extremes; and extremes the SOURCE itself already has in the same
    direction (matching the source's idiomatic extreme — e.g. triplet_share on a swing tune — is
    coherence, not new degeneracy)."""
    out=[]
    for a in AXES:
        if a in LENGTH_AXES: continue
        if prof[a]<=5 or prof[a]>=95:
            v=float(m[a])
            if a in GC and genre in GC[a] and GC[a][genre]["p25"]<=v<=GC[a][genre]["p75"]: continue
            if src_prof is not None:
                sp=src_prof.get(a, 50)
                if (prof[a]<=5 and sp<=15) or (prof[a]>=95 and sp>=85): continue   # source shares this extreme
            out.append((a.split('_',1)[1], prof[a]))
    return out
def sounding_bars(song): return sorted({e["bar"] for e in song.events})
def bar_pcs(song, b):
    w=defaultdict(float)
    for e in song.events:
        if e["bar"]==b: w[e["pc"]]+=e["dur"]
    return frozenset(pc.prominent_pcs(w))
def pcj(a,b):
    if not a or not b: return 0.0
    return len(a&b)/len(a|b)

def main(sid, typ, rpath):
    case = json.loads((OUT/f"{sid}_{typ}_case.json").read_text())
    B = case["bands"]
    src = Song(GRAMMAR/f"{sid}.txt"); reg = Song(rpath)
    sfp = np.array([case["source_fp"][a] for a in AXES],float)
    rfp, rm = fp_vec(rpath); rprof={a:int(rfp[i]) for i,a in enumerate(AXES)}
    D = dist_style(rfp, sfp)        # coherence over length-stable STYLE axes
    rbars = sorted({e["bar"] for e in reg.events}); nrb=len(rbars)

    # non-degeneracy (genre-aware C1 on the region; source-shared idiomatic extremes don't count)
    ext = ga_extremes(rprof, rm, case["genre"], case["source_fp"]); c1 = len(ext) <= B["C1_MAX_EXTREMES"]
    # genuine novelty: copy_risk note-overlap vs the SOURCE (slide) + vs corpus
    risk = cr.copy_risk(rpath, cited=[sid], ref=GRAMMAR/f"{sid}.txt", vs_corpus=True, threshold=B["NOVELTY_MAX"])
    vs_source = max(risk["ref"]["overlap_slid"], risk["max_cited"]["overlap"])
    vs_corpus = risk["max_corpus"]["overlap"]; corp_song = risk["max_corpus"]["song"]
    novel = vs_source < B["NOVELTY_MAX"] and vs_corpus < B["NOVELTY_MAX"]
    # boundary continuity (voice compatibility + tonal continuity at the seam(s)), using SOUNDING bars
    # (skip silent bars — many songs open/close on an empty 'breath' bar, which is not a real jolt).
    svoices=set(case["voices"]); rvoices=set(reg.voices)
    vj = len(svoices&rvoices)/len(svoices|rvoices) if (svoices|rvoices) else 0
    sb_src=sounding_bars(src); rfirst=rbars[0]; rlast=rbars[-1]
    def src_first_after(k): return next((b for b in sb_src if b>=k), sb_src[-1])
    def src_last_before(k): return next((b for b in reversed(sb_src) if b<=k), sb_src[0])
    if typ=="continuation":  seams=[(bar_pcs(src,sb_src[-1]), bar_pcs(reg,rfirst))]            # src last sounding -> region start
    elif typ=="prefix":      seams=[(bar_pcs(reg,rlast), bar_pcs(src,sb_src[0]))]              # region end -> src first sounding
    else:  # insertion: src last-sounding<=k -> region start ; region end -> src first-sounding>k
        k=case["insertion_bar"]; seams=[(bar_pcs(src,src_last_before(k)), bar_pcs(reg,rfirst)),
                                         (bar_pcs(reg,rlast), bar_pcs(src,src_first_after(k+1)))]
    bscores=[pcj(a,b) for a,b in seams]; bmin=min(bscores) if bscores else 0
    boundary_ok = vj>=0.5 and bmin>=B["BOUND_PC_MIN"]
    coheres = D <= B["COHERE_MAX"]
    region_ok = B["REGION_MIN"] <= nrb <= B["REGION_MAX"]

    verdict = coheres and c1 and novel and boundary_ok and region_ok
    print(f"=== NEWGEN MEASURE — {sid} {typ} — {Path(rpath).name} (genre '{case['genre']}') ===")
    print(f"  region: {nrb} bars (plausible {B['REGION_MIN']}-{B['REGION_MAX']}: {'Y' if region_ok else 'N'})")
    print(f"  COHERES        D(region,source)={D:.1f}  (<= {B['COHERE_MAX']}? {'Y' if coheres else 'N'}; chance {case['ref']['chance']}, neighbor {case['ref']['neighbor']})")
    print(f"  NON-DEGENERATE C1 genre-aware extremes={len(ext)} (<= {B['C1_MAX_EXTREMES']}? {'Y' if c1 else 'N'}) {ext if ext else ''}")
    print(f"  GENUINELY-NEW  copy_risk vs-source={vs_source:.2f} vs-corpus={vs_corpus:.2f}({corp_song})  (< {B['NOVELTY_MAX']}? {'Y' if novel else 'N'})")
    print(f"  BOUNDARY       voice-Jaccard={vj:.2f} seam-pcJaccard={[round(x,2) for x in bscores]} (ok? {'Y' if boundary_ok else 'N'})")
    print(f"  >>> {'PASS — source-coherent, non-degenerate, genuinely-new' if verdict else 'FAIL: '+', '.join(n for n,v in [('coheres',coheres),('non-degenerate',c1),('genuinely-new',novel),('boundary',boundary_ok),('region-len',region_ok)] if not v)}")

    summary=dict(sid=sid, type=typ, region=Path(rpath).name, region_bars=nrb,
                 D_consistency=round(D,1), c1_ext=len(ext), coheres=coheres, nondegen=c1,
                 copy_risk_source=round(vs_source,3), copy_risk_corpus=round(vs_corpus,3),
                 novel=novel, voice_jaccard=round(vj,2), seam_pcj=[round(x,2) for x in bscores],
                 boundary_ok=boundary_ok, region_ok=region_ok, verdict=verdict)
    (OUT/f"{Path(rpath).stem}_measure.json").write_text(json.dumps(summary,indent=2))
    return summary

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
