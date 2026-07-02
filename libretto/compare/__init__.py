"""libretto.compare — Libretto (absolute slot) vs ABC-style (relative duration) onset encoding.

Two things, both about the SAME music in the two representations:

1. **Deterministic cost** (`cost`) — model-free, read off a parsed Song's note structure. ABC's relative onset
   encoding costs O(n) prefix-sum additions to recover beats, N(N-1)/2 edit-blast per duration edit, and a
   vertical-alignment sum to read "what sounds together"; Libretto's absolute slot costs **0** for all three.

       from libretto.compare import encoding_cost, corpus_cost
       c = encoding_cost("libretto/data/grammar/song_0047.txt")
       print(c.onset_recovery, c.edit_blast, c.vertical_align, "vs libretto", c.libretto)

2. **Tool-free reading benchmark** (`benchmark`) — emit the same music as ABC and Libretto with objective
   questions + computed ground truth, so an LLM reader can be scored by musical identity (accuracy) and for
   out-of-meter *hallucination* (a beat that cannot exist in the bar — impossible from an absolute slot). The
   LLM run is external; stimuli, ground truth, scorer, and a self-validating `oracle()` are here.

       from libretto.compare import benchmark as B
       items = B.build(B.HIGH_SIGNAL); assert B.oracle(items)[0]
       abc_prompt, lib_prompt = B.prompts(items[0])

Additive to the frozen core (nothing here is frozen). Full write-ups + real-tune data live in
`paper_data/grammar_compare/`. Shell: ``python -m libretto.compare --help``.
"""
from . import benchmark
from .cost import EncodingCost, corpus_cost, encoding_cost

__all__ = ["encoding_cost", "corpus_cost", "EncodingCost", "benchmark"]
