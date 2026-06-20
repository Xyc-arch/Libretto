# morph — bridge one song's component into another's (song -> song)

Write a transition whose fingerprint travels gradually from song A to song B: the START sounds like
a real component of A, the END like a real component of B, and the middle glides smoothly between
them. The two real component bars are fixed as the exact endpoints; you generate the bars in between.

See `_shared.md` for the grammar format.

Inputs (in CONTEXT):
- `component_A`, `component_B`: the exact real start/end component bars (the anchors — do not alter).
- `rampable_targets`: per-axis A-value -> B-value to interpolate across the transition.
- `transition_bars`: how many bars to generate between the anchors (longer = smoother).
- `key_A/meter_A` and `key_B/meter_B`: reconcile across the glide.

Requirements:
- START close to A (early bars high copy-A), END close to B (late bars high copy-B): a CROSSFADE.
- GRADUAL: per-bar progress A->B monotonic (±0.10 noise) with max step ≤ 0.40 — no jump-cuts.
- Derive the transition material from A's motifs early and B's late (thematic crossfade). Copy is
  RELAXED at the seams (to enable the glide) but the pure-generated middle should stay mostly original.
- Output ONLY the transition bars (between, not including, the two fixed anchors).
