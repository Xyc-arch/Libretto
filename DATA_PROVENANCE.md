# Data provenance

The frozen corpus under `libretto/data/` is curated from the **Clean MIDI subset of the Lakh MIDI Dataset**
(Colin Raffel) — in the dataset author's words, *"a subset of MIDI files with filenames which indicate their
artist and title (with some inaccuracy)."*

- **What we ship:** 314 songs encoded into the Libretto text **grammar** (`data/grammar/song_*.txt`), the frozen
  29-axis distribution (`data/corpus_distribution_314.json`, `data/corpus_fps.json`), per-song artist/title
  metadata (`data/answer_key/grammar_truth.json`), and the two knowledge bases (`data/composing-kb/`,
  `data/kb_theory/`). The 314 selection and the genre labels are ours; the source MIDIs are from clean_midi.
- **Make-up:** 255 genre-labeled + 59 original = 314 songs (8 genres), skewed toward well-known Western popular
  artists. `song_0014` is a generated piece and is excluded from the corpus.

## Caveats
- These are **community MIDI transcriptions of copyrighted compositions**, re-encoded as text grammar and
  provided here **for research reproducibility** (the same posture as the Lakh MIDI Dataset itself). The
  underlying musical works remain the property of their respective rights holders.
- Artist/title (and hence our genre labels) inherit Lakh's matching noise ("with some inaccuracy").
- Known near-duplicate transcriptions exist (a Lakh artifact); the copy gate is calibrated to account for them.

## License
- **Code:** MIT (see `LICENSE`).
- **Dataset/metadata lineage:** Lakh MIDI Dataset is released under **CC-BY 4.0**.

## Cite
Colin Raffel. *Learning-Based Methods for Comparing Sequences, with Applications to Audio-to-MIDI Alignment and
Matching.* PhD thesis, Columbia University, 2016. (Lakh MIDI Dataset — `clean_midi` subset.)
Project page: https://colinraffel.com/projects/lmd/
