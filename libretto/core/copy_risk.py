#!/usr/bin/env python3
"""copy_risk.py — STRICT note-level copy-risk metric for generated pieces.

The variation work showed bar-level copy checks UNDERSTATE reuse (bar-copy can read 0% while ~50% of
notes are reused, because a bar is only "copied" if identical across ALL voices at once). This metric
measures reuse at NOTE granularity: the share of a generated piece's exact (bar, onset, pitch) notes that
also appear in a real song, aligned bar-for-bar.

copy_risk(piece) = max over candidate real songs S of note_overlap(piece, S), where
    note_overlap(piece, S) = |{notes of piece that coincide with a note of S at the same intra-bar
                               position and pitch, under the best whole-piece bar alignment}| / |notes of piece|
Computed against (a) the KB-CITED example songs (the explicit reproduction risk — the generator saw
those bars) with a full bar-offset slide, and (b) the CORPUS generally (pre-filtered, then slid).

A from-scratch generation has no "stay recognizable" reason to retain notes, so the gate is STRICT:
copy_risk must stay BELOW ~0.30 (vs 0.55 for recognizable variation). Report the max single-song overlap
and WHICH song; flag/reject pieces above the threshold.

Usage:
  python3 copy_risk.py <piece.txt> [--cited s1,s2,..] [--ref real_region.txt] [--threshold 0.30] [--no-corpus]
"""
import json, sys, re
from collections import defaultdict
import os
from pathlib import Path
from .understanding_probe import Song

SCRIPT = Path(os.environ.get("LIBRETTO_DATA") or (Path(__file__).resolve().parent.parent / "data"))
GRAMMAR = SCRIPT / "grammar"
# Empirical calibration (max single-song note-overlap between UNRELATED real corpus songs, n=18 sample):
# mean 0.18, median 0.12, p90 0.22 — i.e. ~0.22 is the COINCIDENTAL idiom-sharing floor (common diatonic
# material at common beat positions). (Outlier: song_0048 vs song_0110 = 0.87 — a genuine near-duplicate,
# both "U2 — With or Without You".) So a from-scratch piece below ~0.22 is at the coincidental floor;
# the strict gate 0.30 (~1.4x the floor) flags pieces with materially more single-song overlap than idiom.
COINCIDENTAL_FLOOR = 0.22
STRICT_THRESHOLD = 0.30        # from-scratch generation: note-overlap with any single song must stay below this
PREFILTER_TOPK = 25            # corpus songs to slide after a cheap bag pre-score

def piece_notes(path):
    """Return (by_bar: bar->set{(onset,pitch)}, bag: set{(onset,pitch)}, total_notes)."""
    s = Song(path)
    by_bar = defaultdict(set); bag = set(); total = 0
    for e in s.events:
        t = (round(e["onb"], 2), e["midi"]); by_bar[e["bar"]].add(t); bag.add(t); total += 1
    return by_bar, bag, total

_CORPUS = None
def load_corpus():
    global _CORPUS
    if _CORPUS is None:
        _CORPUS = {}
        for f in sorted(GRAMMAR.glob("song_*.txt")):
            if f.stem == "song_0014": continue   # the generated/excluded song
            bb, bag, tot = piece_notes(f)
            _CORPUS[f.stem] = (bb, bag, tot)
    return _CORPUS

def aligned_overlap(gen_bb, gen_total, song_bb, offset):
    """Fraction of gen notes matched when gen bar b is aligned to song bar b+offset."""
    if gen_total == 0: return 0.0
    hit = 0
    for b, notes in gen_bb.items():
        sb = song_bb.get(b + offset)
        if sb: hit += len(notes & sb)
    return hit / gen_total

def slide_overlap(gen_bb, gen_total, song_bb):
    """Max note-overlap over all whole-piece bar alignments (offset-invariant)."""
    if not gen_bb or not song_bb: return 0.0, 0
    gmin, gmax = min(gen_bb), max(gen_bb); smin, smax = min(song_bb), max(song_bb)
    best, besto = 0.0, 0
    for offset in range(smin - gmax, smax - gmin + 1):
        ov = aligned_overlap(gen_bb, gen_total, song_bb, offset)
        if ov > best: best, besto = ov, offset
    return best, besto

def copy_risk(piece_path, cited=None, ref=None, vs_corpus=True, threshold=STRICT_THRESHOLD):
    gen_bb, gen_bag, gen_total = piece_notes(piece_path)
    res = {"piece": Path(piece_path).name, "n_notes": gen_total, "threshold": threshold}

    # (ref) direct vs a specific reference (e.g. the held-out real region a gap-gen should NOT reproduce)
    if ref:
        rb, rbag, rt = piece_notes(ref)
        ov0 = aligned_overlap(gen_bb, gen_total, rb, 0)           # both files start at bar 1 → aligned
        ovs, off = slide_overlap(gen_bb, gen_total, rb)
        res["ref"] = {"name": Path(ref).name, "overlap_aligned": round(ov0, 3), "overlap_slid": round(ovs, 3)}

    # (a) KB-cited songs — full slide
    cited_max = (None, 0.0)
    for sid in (cited or []):
        p = GRAMMAR / f"{sid}.txt"
        if not p.exists(): continue
        sb, _, _ = piece_notes(p)
        ov, _ = slide_overlap(gen_bb, gen_total, sb)
        if ov > cited_max[1]: cited_max = (sid, ov)
    res["max_cited"] = {"song": cited_max[0], "overlap": round(cited_max[1], 3)}

    # (b) corpus — cheap bag pre-score, then slide the top-K candidates
    corpus_max = (None, 0.0)
    if vs_corpus:
        corp = load_corpus()
        pre = sorted(((len(gen_bag & bag) / max(1, len(gen_bag)), sid) for sid, (bb, bag, t) in corp.items()),
                     reverse=True)[:PREFILTER_TOPK]
        for _, sid in pre:
            sb = corp[sid][0]
            ov, _ = slide_overlap(gen_bb, gen_total, sb)
            if ov > corpus_max[1]: corpus_max = (sid, ov)
        res["max_corpus"] = {"song": corpus_max[0], "overlap": round(corpus_max[1], 3)}

    overall = max(cited_max[1], corpus_max[1],
                  res.get("ref", {}).get("overlap_slid", 0.0))
    res["copy_risk"] = round(overall, 3)
    res["pass"] = overall < threshold
    return res

def _fmt(r):
    line = f"{r['piece']:<34} risk={r['copy_risk']:.2f} {'PASS' if r['pass'] else 'FAIL'}"
    if "ref" in r: line += f" | vs-ref({r['ref']['name']}) aligned={r['ref']['overlap_aligned']:.2f} slid={r['ref']['overlap_slid']:.2f}"
    if "max_cited" in r and r["max_cited"]["song"]: line += f" | cited-max {r['max_cited']['overlap']:.2f}({r['max_cited']['song']})"
    if "max_corpus" in r: line += f" | corpus-max {r['max_corpus']['overlap']:.2f}({r['max_corpus']['song']})"
    return line

if __name__ == "__main__":
    argv = sys.argv[1:]
    def opt(name, default=None):
        if name in argv:
            i = argv.index(name); v = argv[i+1]; del argv[i:i+2]; return v
        return default
    cited = opt("--cited"); ref = opt("--ref"); thr = float(opt("--threshold", STRICT_THRESHOLD))
    no_corpus = "--no-corpus" in argv
    if no_corpus: argv.remove("--no-corpus")
    piece = argv[0]
    r = copy_risk(piece, cited=cited.split(",") if cited else None, ref=ref,
                  vs_corpus=not no_corpus, threshold=thr)
    print(_fmt(r))
    print(json.dumps(r, indent=2))
