#!/usr/bin/env python3
"""chunked.py — autoregressive CHUNKED newgen: build a full piece as a chain of validated continuations
(gaptask-style anchoring) instead of one blind whole-piece generation.

Why: blind whole-piece newgen reliably fails the per-axis non-degeneracy gate (thin texture, etc.), and an
unanchored generator also can't infer conventions from context. Generating in chunks where each chunk is
(a) validated on the LOCAL axes and (b) conditioned on the validated piece-so-far turns newgen into a chain
of anchored continuations — each step lands in-distribution, and chunk-to-chunk diversity supplies the
whole-piece-only axes (sectioning, within-song / density variation, novelty) that a single flat pass can't.

Per-chunk gate = LOCAL axes only (rhythm / harmony / melody / texture) + note-level copy_risk < 0.30. The
whole-piece-only axes are judged on the ASSEMBLED piece via the standard newgen gate (see refine_loop /
newgen_measure). Plug any libretto.generation Generator.
"""
import json, re
from pathlib import Path
import numpy as np
import libretto
from libretto.core import Song, metrics_for, copy_risk, axis_feedback as afb
from . import refine_loop as nrl

DATA = libretto.data_root()
CANON = json.loads((DATA / "corpus_distribution_314.json").read_text())
AXES = CANON["axes_order"]; COLS = {a: np.array(CANON["axes"][a]["values"], float) for a in AXES}
GC = CANON["genre_conditioned"]; SPLIT = list(GC.keys())
# axes that need the WHOLE piece to be meaningful — judged on the assembled piece, not per chunk:
WHOLE_ONLY = {"form_self_similarity", "form_novelty_rate", "form_distinct_bar_frac",
              "form_section_per100bars", "within_song_variation", "rhy_density_variability"}
LOCAL_AXES = [a for a in AXES if a not in WHOLE_ONLY]
COPY_THRESHOLD = 0.30
DEFAULT = dict(chunk_bars=16, n_chunks=5, seam_bars=6, max_retry=2)


def _blocks(t):
    h, b, cur = [], [], None
    for ln in t.splitlines():
        if ln.startswith("@"):
            if cur is not None: b.append(cur)
            cur = [ln]
        elif cur is None: h.append(ln)
        else: cur.append(ln)
    if cur is not None: b.append(cur)
    return h, b


def _emit(header_line, voices_line, blocks):
    out = [re.sub(r"BARS:\s*\d+", f"BARS: {len(blocks)}", header_line), voices_line]
    for i, blk in enumerate(blocks, 1):
        bb = list(blk); bb[0] = re.sub(r"^@\d+", f"@{i}", bb[0]); out += bb
    return "\n".join(out) + "\n"


def gband(ax, genre):
    b = GC[ax][genre]; return round(b["p25"], 2), round(b["p50"], 2), round(b["p75"], 2)


def chunk_fitness(chunk_path, genre):
    """Per-chunk gate: genre-aware non-degeneracy on LOCAL axes + copy_risk vs corpus. Leakage-free."""
    m = metrics_for(Song(chunk_path), chunk_path)
    ext = []
    for a in LOCAL_AXES:
        v = float(m[a]); pct = round(float((COLS[a] <= v).mean() * 100))
        if pct <= 5 or pct >= 95:
            if a in GC and genre in GC[a] and GC[a][genre]["p25"] <= v <= GC[a][genre]["p75"]: continue
            ext.append((a, pct))
    cr = copy_risk(chunk_path, vs_corpus=True)["copy_risk"]
    nb = len(sorted({e["bar"] for e in Song(chunk_path).events}))
    return dict(bars=nb, local_extremes=ext, c_local_pass=len(ext) <= 3,
                copy_risk=cr, copy_pass=cr < COPY_THRESHOLD, ok=(len(ext) <= 3 and cr < COPY_THRESHOLD))


def chunk_feedback(fit):
    lines = []
    for a, pct in fit["local_extremes"]:
        lines.append(afb.explain(a, "increase" if pct <= 50 else "decrease", pct=pct))
    if not fit["copy_pass"]:
        lines.append(f"COPY: copy_risk {fit['copy_risk']:.2f} ≥ {COPY_THRESHOLD}; invent fresher material.")
    return lines


def _bands_text(genre):
    return "\n".join(f"    - {ax.split('_',1)[1]}: stay in [{gband(ax,genre)[0]},{gband(ax,genre)[2]}], aim ~{gband(ax,genre)[1]}"
                     for ax in SPLIT)


def opening_prompt(genre, chunk_bars, shared_format, style_ref=""):
    ref = f"\n{style_ref}\n" if style_ref else ""
    return (f"# newgen (chunked) — OPENING section, genre={genre}\n{shared_format}\n{ref}\n"
            f"Compose the OPENING {chunk_bars} bars of a {genre} piece. Full multi-voice texture (real "
            f"block chords with `+`, not single lines), a real groove (on-beat anchored on 1-indexed slots "
            f"1/5/9/13 with a NORMAL amount of off-beat motion — not all-on-beat, not all-off-beat), varied "
            f"durations, healthy chord width. Aim each genre split-axis at its mid-band:\n{_bands_text(genre)}\n\n"
            f"Pick a KEY/METER/TEMPO/GRID and keep them fixed for the whole piece. Output ONLY a grammar block "
            f"(header BARS:{chunk_bars} + VOICES + {chunk_bars} bars). No prose/fences.")


def continuation_prompt(genre, chunk_bars, seam_grammar, k, n_chunks, shared_format):
    return (f"# newgen (chunked) — CONTINUATION, section {k} of {n_chunks}, genre={genre}\n{shared_format}\n\n"
            f"Below are the LAST bars of the piece so far. Continue with the NEXT {chunk_bars} bars in the SAME "
            f"key/meter/tempo/voices, coherent at the seam, but make this a DISTINCT section (new material, "
            f"different from the previous section — so the whole piece varies). Full texture, on-beat groove on "
            f"1-indexed slots 1/5/9/13 with normal off-beat motion, mid-band on the genre split-axes:\n"
            f"{_bands_text(genre)}\n\n### PIECE SO FAR (continue FROM here, do not repeat):\n{seam_grammar}\n"
            f"Output ONLY the next {chunk_bars} bars as a grammar block (same header KEY/METER/TEMPO/GRID, "
            f"BARS:{chunk_bars}, same VOICES). No prose/fences.")


def assemble(chunk_texts):
    """Concatenate validated chunk grammars into one full-piece grammar (shared header from chunk 1)."""
    h0, _ = _blocks(chunk_texts[0]); voices = next((l for l in h0 if l.startswith("VOICES:")), "")
    allb = []
    for t in chunk_texts:
        allb += _blocks(t)[1]
    return _emit(h0[0], voices, allb)


def seam(piece_text, seam_bars):
    h, b = _blocks(piece_text); voices = next((l for l in h if l.startswith("VOICES:")), "")
    return _emit(h[0], voices, b[-seam_bars:])


class ChunkedNewgen:
    """Autoregressive chunked newgen driven by a Generator. Each chunk is retried (with axis feedback) until
    it passes the local gate, then the validated piece-so-far seam conditions the next chunk."""

    def __init__(self, generator, chunk_bars=DEFAULT["chunk_bars"], n_chunks=DEFAULT["n_chunks"],
                 seam_bars=DEFAULT["seam_bars"], max_retry=DEFAULT["max_retry"]):
        self.gen = generator; self.cb = chunk_bars; self.nc = n_chunks
        self.seam_bars = seam_bars; self.max_retry = max_retry
        self.shared = (Path(libretto.__file__).resolve().parent / "generation" / "prompts" / "_shared.md").read_text()

    def _make_chunk(self, base_prompt, genre, context):
        corrections = []
        for attempt in range(self.max_retry + 1):
            prompt = base_prompt + ("\n\n## FIX (your last attempt failed the local checks):\n" +
                                    "\n".join(f"  - {c}" for c in corrections) if corrections else "")
            grammar = self.gen.generate(prompt, dict(context or {}))
            tmp = Path(context.get("workdir", ".")) / "_chunk_tmp.txt"; tmp.write_text(grammar, encoding="utf-8")
            fit = chunk_fitness(tmp, genre); tmp.unlink(missing_ok=True)
            if fit["ok"] or attempt == self.max_retry:
                return grammar, fit, attempt
            corrections = chunk_feedback(fit)

    def run(self, genre, workdir=".", label="chunked"):
        workdir = Path(workdir); ctx = {"workdir": str(workdir)}
        chunks, log = [], []
        # chunk 1 — opening (retrieval is mandatory: inject the genre's KB concepts + prototypical exemplars)
        try:
            from . import retrieval as R
            style_ref = R.build_retrieval(genre)["text"]
        except Exception:
            style_ref = ""
        g1, f1, a1 = self._make_chunk(opening_prompt(genre, self.cb, self.shared, style_ref), genre, ctx)
        (workdir / f"{label}_chunk1.txt").write_text(g1, encoding="utf-8"); chunks.append(g1)
        log.append(dict(chunk=1, retries=a1, **{k: f1[k] for k in ("bars", "copy_risk", "ok")},
                        n_local_ext=len(f1["local_extremes"])))
        # chunks 2..N — continuations conditioned on the assembled seam
        for k in range(2, self.nc + 1):
            sm = seam(assemble(chunks), self.seam_bars)
            gk, fk, ak = self._make_chunk(continuation_prompt(genre, self.cb, sm, k, self.nc, self.shared), genre, ctx)
            (workdir / f"{label}_chunk{k}.txt").write_text(gk, encoding="utf-8"); chunks.append(gk)
            log.append(dict(chunk=k, retries=ak, **{kk: fk[kk] for kk in ("bars", "copy_risk", "ok")},
                            n_local_ext=len(fk["local_extremes"])))
        full = assemble(chunks); fp = workdir / f"{label}_full.txt"; fp.write_text(full, encoding="utf-8")
        whole = nrl.piece_fitness(fp, genre=genre)   # standard whole-piece gate (incl. the whole-only axes)
        return dict(full_path=str(fp), whole_fitness=whole, chunks=log)
