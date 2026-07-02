# libretto.compare — Libretto vs ABC-style onset encoding

Why the grammar uses an **absolute slot** for onset instead of ABC's **relative duration**. Two parts, both on
the *same music* in the two representations; additive to the frozen core (nothing here is frozen).

## 1. Deterministic cost (`cost.py`) — model-free

`encoding_cost(song)` reads a parsed `Song` and returns, for the ABC-style relative encoding vs Libretto's
absolute slot:

| cost | what it is | ABC (relative) | Libretto (slot) |
|---|---|---|---|
| `onset_recovery` | additions to label every note's beat (running within-bar prefix-sum) | Σ (notes−1) | **0** |
| `edit_blast` | onsets re-derived when one duration edit shifts a voice's tail | Σ N(N−1)/2 | **0** |
| `vertical_align` | additions to align voices = read "what sounds together" | Σ prefix-sums | **0** |

```python
from libretto.compare import encoding_cost, corpus_cost
c = encoding_cost("libretto/data/grammar/song_0047.txt")
print(c.onset_recovery, c.edit_blast, c.vertical_align, "vs", c.libretto)
tot, rows = corpus_cost(sorted((data_root()/"grammar").glob("*.txt")))   # whole corpus
```

## 2. Tool-free reading benchmark (`benchmark.py`)

Same music emitted as ABC **and** Libretto, with objective questions + computed ground truth, so an LLM reader
(reading only — no code) is scored by musical identity. Tasks in `TASKS`: T1 onset, T2 alignment, T3 chord,
T4 voice-leading, T5 copy-risk, T6 edit blast-radius, T7 drift. `build_hallucination()` makes dense/deep passages
for a **quick-read** prompt, where ABC over-accumulation yields *out-of-meter* answers ("beat 7") that an absolute
slot cannot represent.

```python
from libretto.compare import benchmark as B
items = B.build(B.HIGH_SIGNAL, seeds=(0, 1))     # stimuli + questions + ground truth
assert B.oracle(items)[0]                        # self-check: ground truth scores 100%, 0 impossible
abc_prompt, lib_prompt = B.prompts(items[0])     # feed to any tool-free reader
# collect replies as {item_id: {'abc': text, 'lib': text}} and:
report = B.summarize(items, replies)             # per-condition accuracy + T1 impossible-answer rate
```

`impossible(item, qtype, answer)` flags the hallucination metric (a beat/bar that cannot exist) — always `False`
for a Libretto slot by construction.

## Shell
```
python -m libretto.compare cost                     # corpus totals: ABC additions vs Libretto 0
python -m libretto.compare cost <song.txt> ...      # per-song
python -m libretto.compare benchmark --oracle       # build high-signal set + self-check
python -m libretto.compare benchmark --hallucination --out /tmp/hallu   # dense quick-read prompts
```

## Scope & caveats
The deterministic cost is the **robust, model-independent** result (a property of the encoding). The benchmark's
LLM numbers are **illustrative** (small n, one reader model), and the hallucination effect is a *quick-read*
phenomenon — with full step-by-step work ABC nears parity. ABC's honest advantage is token terseness. Full
write-ups, real Nottingham-tune data, and figures are in `paper_data/grammar_compare/`.
