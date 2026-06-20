---
name: composing-kb
description: A grep-able, index-driven knowledge base of 28 cross-genre concepts + 6 jazz-specialized concepts (34 total) for an AI composing agent, re-grounded on 314 real songs across 8 genres (pop/rock, soul/funk/R&B, jazz, classical, electronic/dance, folk/country, film/score, latin/reggae/world). This SKILL.md is the INDEX (cross-reference map from genre / music-theory / compositional-task / musical-feature to concept entries). The concepts live in the topic .txt files; corpus-grounded target BANDS for the composing loop live in dosage.txt. Use when composing or arranging and you need grounded, generatively-framed building blocks. Retrieval is lookup (grep the map → load the entry), not embeddings.
---

# Composing KB — index

This is the **index**, not the content. It routes a composing agent from an access path
(a genre, a theory term, a task, or a feature) to the concept entries that help, and tells
it which `.txt` file they live in. Read this first; then load only the entries you need.

## How to retrieve (lookup, not embeddings)
1. Decide your access path: **genre**, **theory concept**, **compositional task**, or **musical feature**.
2. Find matching concept **IDs** in the corresponding cross-reference map below.
3. Load each entry from its topic file, e.g.:
   `grep -A24 "CONCEPT: H-DOM7" composing-kb/harmony.txt`
   (or open the file and jump to the `CONCEPT:` line). Each entry has `WHAT` (incl. theory),
   tag lines, a real corpus `EXAMPLE` (song_id + bar), and a `COMPOSE` (how to generate it).
4. To browse by tag directly in the txt files: `grep -il "soul" composing-kb/*.txt`,
   `grep -n "THEORY:.*secondary" composing-kb/*.txt`, `grep -n "ROLE:.*cadence" composing-kb/*.txt`.

## Honest framing
- **Descriptive of THIS corpus**, not universal rules. Re-grounded on **314 real songs across 8
  genres** (pop/rock, soul/funk/R&B, jazz, classical, electronic/dance, folk/country, film/score,
  latin/reggae/world), selection-biased toward well-known artists. These are building blocks *this
  music uses*, **not** requirements for good music. They are **structural, not quality-defining** —
  using them does not make music good; they describe what's there.
- **Grounded**: every concept cites real tokens (song_id + bar); harmony is verified from actual
  pitch classes, not the unreliable `[chord]` labels. The generated piece (song_0014) is excluded.
- **Core-idiom vs occasional-color** (the `STATUS` tag): **core-idiom** = attested in ≥50% of the
  **314** songs (a default move of the idiom); **occasional-color** = a less common device (reach
  for it deliberately). Counts (re-grounded /314) are on each entry and in the registry below.
- **Genre-specific patterns** (flagged `*genre-specific*` / `GENRE-SPECIFIC` on the entry): some
  concepts are pervasive in some genres and rare in others (e.g. V-ROLES pop 97% vs classical 23%;
  M-SIGH classical 93% vs electronic 29%; M-GAPFILL jazz 93%; H-AUG classical/jazz vs folk 12%). For
  these, the per-genre attestation is on the entry — apply them by target genre, not globally.
- **Dosage bands** (`dosage.txt`): corpus-grounded [p25 · p50 · p75] target VALUES per axis that the
  composing loop steers toward — the idiomatic BAND, NOT the mean. The split axes (syncopation,
  triplet_share, dim/aug, distinct_bar_frac) carry **genre-conditioned** bands there. Steer to the
  band of the genre you're writing.

## Concept registry (ID · name · file · status · attestation — re-grounded on 314 songs)
Attestation is /314 (was /59). `*genre-specific*` = per-genre attestation varies widely (≥50 pts);
see the entry's `ATTEST` line for the per-genre breakdown.
| ID | Concept | File | Status | Attest /314 |
|----|---------|------|--------|--------|
| R-SYNCO | Syncopation | rhythm_groove.txt | core-idiom | 311/314 |
| R-STRAIGHT | Straight (binary) subdivision | rhythm_groove.txt | core-idiom | 269/314 |
| H-DIM | Diminished passing sonority | harmony.txt | core-idiom | 264/314 |
| H-DOM7 | Dominant-seventh sonority | harmony.txt | core-idiom | 254/314 |
| V-ROLES | Bass/chordal/melody role stratification | voicing.txt | core-idiom | 253/314 *genre-specific* |
| H-FOURTHS | Functional root motion up a 4th (V–I / ii–V–I) | harmony.txt | core-idiom | 247/314 |
| R-OSTINATO | Groove ostinato | rhythm_groove.txt | core-idiom | 213/314 *genre-specific* |
| M-SIGH | Descending-step 'sigh' resolution | melody.txt | core-idiom | 211/314 *genre-specific* |
| H-PEDAL | Bass pedal point | harmony.txt | core-idiom | 207/314 |
| V-WIDE | Wide multi-octave chord voicing | voicing.txt | core-idiom | 195/314 *genre-specific* |
| M-MOTIF | Repeated motivic cell | melody.txt | core-idiom | 184/314 |
| M-GAPFILL | Leap then step-back (gap-fill) | melody.txt | core-idiom | 184/314 *genre-specific* |
| V-DOUBLE | Unison / octave doubling | voicing.txt | core-idiom | 173/314 |
| F-REPRISE | Verbatim sectional reprise | form.txt | core-idiom ↑ | 157/314 |
| R-ROOTPULSE | Root-pulse / four-on-the-floor bass | rhythm_groove.txt | occasional-color | 151/314 |
| H-AUG | Augmented-triad passing sonority | harmony.txt | occasional-color | 137/314 *genre-specific* |
| H-DESCBASS | Descending stepwise bass line (line-cliché/lament) | harmony.txt | occasional-color | 116/314 |
| M-STEP | Predominantly stepwise melodic motion | melody.txt | occasional-color | 109/314 |
| F-OUTRO | Thinning / fade outro | form.txt | occasional-color | 93/314 |
| F-INTRO | Single-voice / sparse intro | form.txt | occasional-color | 59/314 |
| V-PARALLEL | Parallel thirds / sixths | voicing.txt | occasional-color | 50/314 |
| R-TRIPLET | Triplet / compound subdivision (shuffle, 12/8) | rhythm_groove.txt | occasional-color | 45/314 *genre-specific* |
| R-DURVAR | Duration variety (mix long & short) | rhythm_groove.txt | core-idiom | 311/314 |
| F-SECTIONS | Multi-sectional form (contrast) | form.txt | core-idiom | 293/314 |
| H-RHYTHM | Harmonic rhythm / chord-change rate | harmony.txt | core-idiom | 289/314 |
| M-RANGE | Melodic range & mixed-interval contour | melody.txt | core-idiom | 250/314 *genre-specific* |
| R-DENSITY | Density ebb & flow | rhythm_groove.txt | core-idiom | 226/314 |
| H-PALETTE | Pitch-class palette breadth (chromatic color) | harmony.txt | core-idiom | 175/314 *genre-specific* |

The 6 rows above (R-DURVAR · F-SECTIONS · H-RHYTHM · M-RANGE · R-DENSITY · H-PALETTE) are the **new
axis-coverage concepts** added in the 314 re-grounding (Part 2 P1) — one consistent lever per
previously-uncovered fingerprint axis (harmonic rhythm, palette/chromaticism, duration variety,
density, melodic range, sectional form), so the composing loop no longer reinvents dosage each round.
Grounded by `add_concepts.py` (detectors + real citations). Note: V-DOUBLE is now **attestation-only**
(its axis tex_doubling_ratio was dropped; the loop does not steer it).

### Genre-specialized: JAZZ (demonstration of genre depth — `jazz.txt`)
Six jazz-specific concepts, grounded in the 28 jazz-bucket corpus songs (attestation is /28 jazz songs,
NOT /314), with JAZZ-conditioned dosage. Use these (plus H-DOM7/H-PALETTE/R-TRIPLET/M-GAPFILL) when the
target genre is jazz. This is a scoped demonstration that the architecture supports genre-specialized
guidance — not a build-out of all genres.
| ID | Concept | File | Status | Attest /28 jazz |
|----|---------|------|--------|--------|
| J-BEBOP | Bebop melody (gap-fill + chromatic approach) | jazz.txt | jazz-idiom | 26/28 |
| J-SWING | Swing / triplet feel | jazz.txt | jazz-idiom | 23/28 |
| J-COMP | Comping (sparse syncopated voicings) | jazz.txt | jazz-idiom | 21/28 |
| J-WALK | Walking bass | jazz.txt | jazz-idiom | 18/28 |
| J-EXT | Extended / altered harmony (9/11/13, alt dom) | jazz.txt | jazz-idiom | 17/28 |
| J-IIVI | ii–V–I and turnarounds | jazz.txt | jazz-idiom | 15/28 |

**Re-grounding note (314 vs 59):** attestation softened across the board (most patterns −1 to −16
pts) as non-pop genres diluted pop-centric devices, but no pattern dropped out. **One status change:**
F-REPRISE rose occasional→**core** (42%→50%) — literal reprise is more pervasive across the wider
corpus. Patterns now near the boundary (occasional): R-ROOTPULSE 48%, H-AUG 44%, H-DESCBASS 37%,
M-STEP 35%. Adding genuinely NEW patterns would require new detectors in `pattern_catalog.py` (not
invented here). Source of these numbers: `../answer_key/kb_regrounding.json`.

---

## MAP 1 — by GENRE  (genre → concepts to reach for)
| Genre | Concept IDs |
|-------|-------------|
| soul / R&B | R-SYNCO, R-OSTINATO, H-DOM7, H-DIM, H-FOURTHS, H-DESCBASS, M-SIGH, V-PARALLEL, V-DOUBLE |
| funk | R-SYNCO, R-OSTINATO, R-ROOTPULSE, H-PEDAL, H-DOM7, V-DOUBLE |
| disco | R-ROOTPULSE, R-SYNCO, R-OSTINATO, R-STRAIGHT, V-WIDE |
| rock | R-STRAIGHT, R-OSTINATO, H-PEDAL, V-ROLES, V-DOUBLE, R-SYNCO, M-GAPFILL |
| pop | V-ROLES, R-SYNCO, R-STRAIGHT, M-MOTIF, M-SIGH, F-REPRISE, H-FOURTHS |
| folk | M-STEP, R-ROOTPULSE, V-PARALLEL, V-ROLES, R-STRAIGHT |
| ballad | R-TRIPLET, H-DESCBASS, M-SIGH, H-DIM, V-WIDE, M-STEP |
| jazz | **J-EXT, J-IIVI, J-SWING, J-BEBOP, J-COMP, J-WALK** (jazz.txt), + H-DOM7, H-PALETTE, R-TRIPLET, M-GAPFILL, M-RANGE |
| jazz-pop / standards | H-FOURTHS, H-DOM7, H-DIM, H-AUG, M-SIGH, J-EXT, J-IIVI |
| gospel | H-DOM7, H-DIM, V-WIDE, R-TRIPLET, H-FOURTHS |
| reggae | R-OSTINATO, H-PEDAL, R-ROOTPULSE, R-SYNCO |
| prog | H-PEDAL, H-DESCBASS, F-INTRO, F-REPRISE |
| vocal-harmony / doo-wop | V-PARALLEL, V-DOUBLE, M-SIGH |
| latin | R-SYNCO, R-OSTINATO |

## MAP 2 — by MUSIC-THEORY CONCEPT  (theory term → concept)
| Theory term | Concept IDs |
|-------------|-------------|
| secondary dominant / dominant 7th / V7 | H-DOM7 |
| ii–V–I / cadence / circle of fifths / functional harmony | H-FOURTHS |
| diminished chord / passing chord / leading-tone | H-DIM |
| augmented chord / raised fifth / V+ | H-AUG |
| line cliché / lament bass / descending tetrachord | H-DESCBASS |
| pedal point (tonic/dominant pedal) | H-PEDAL |
| appoggiatura / suspension / 2–1 resolution | M-SIGH |
| motif / motivic development | M-MOTIF |
| gap-fill / leap recovery / melodic arch | M-GAPFILL |
| conjunct / stepwise / scalar motion | M-STEP |
| syncopation / anticipation / off-beat accent | R-SYNCO |
| ostinato / riff / vamp | R-OSTINATO |
| four-on-the-floor / steady pulse | R-ROOTPULSE |
| binary subdivision (straight) | R-STRAIGHT |
| compound meter / triplet feel / shuffle / 12-8 | R-TRIPLET |
| strophic / verse-chorus / literal repetition | F-REPRISE |
| homophony / melody+accompaniment / register layering | V-ROLES |
| doubling (unison/octave) | V-DOUBLE |
| parallel motion (3rds/6ths) / planing | V-PARALLEL |
| open / wide voicing / register spread | V-WIDE |
| harmonic rhythm / chords-per-bar / chord-change rate | H-RHYTHM |
| chromaticism / pitch-class palette / non-diatonic color | H-PALETTE |
| rhythmic-value variety / long-vs-short durations | R-DURVAR |
| textural density / dynamic build / arrangement arc | R-DENSITY |
| melodic range / tessitura / step-leap contour | M-RANGE |
| sectional form / verse-chorus / structural contrast | F-SECTIONS |

## MAP 3 — by COMPOSITIONAL TASK  (what you're trying to do → concept)
| Task | Concept IDs |
|------|-------------|
| write a cadence / turnaround | H-FOURTHS, H-DOM7, H-DIM |
| write a chord progression / verse harmony | H-FOURTHS, H-DESCBASS, H-PEDAL, H-DIM |
| harmonize a descending bass line | H-DESCBASS, H-DIM, H-PEDAL |
| add chromatic / harmonic color | H-PALETTE, H-AUG, H-DIM, H-DOM7 |
| set the harmonic rhythm / chords-per-bar | H-RHYTHM, H-PEDAL |
| write a groove / accompaniment bed | R-OSTINATO, R-SYNCO, R-ROOTPULSE, H-PEDAL |
| vary note durations / rhythmic values | R-DURVAR |
| shape density / build & drop / arrangement arc | R-DENSITY |
| write a bass line | R-ROOTPULSE, H-DESCBASS, H-PEDAL, R-OSTINATO |
| choose a feel (straight vs swung) | R-STRAIGHT, R-TRIPLET |
| write a melody / hook | M-MOTIF, M-GAPFILL, M-STEP, M-SIGH, M-RANGE |
| set melodic range / contour | M-RANGE, M-GAPFILL, M-STEP |
| end a phrase | M-SIGH, H-FOURTHS |
| write an intro | F-INTRO, H-PEDAL, R-OSTINATO |
| write an outro / ending | F-OUTRO, H-FOURTHS |
| build song form / sections | F-SECTIONS, F-REPRISE, F-INTRO, F-OUTRO |
| voice a chord / spacing | V-WIDE, V-ROLES |
| arrange voices / texture | V-ROLES, V-DOUBLE, V-PARALLEL |
| thicken / reinforce a line | V-DOUBLE, V-PARALLEL, V-WIDE |
| write backing harmony / harmonize a line | V-PARALLEL, V-DOUBLE |

## MAP 4 — by MUSICAL FEATURE  (a sound you want → concept)
| Feature / vibe | Concept IDs |
|----------------|-------------|
| off-beat / syncopated feel | R-SYNCO |
| triplet / shuffle / swung feel | R-TRIPLET |
| driving / dance pulse | R-ROOTPULSE |
| repeated riff / hypnotic vamp | R-OSTINATO |
| static / anchored bass | H-PEDAL |
| descending bass / brooding | H-DESCBASS |
| dominant / bluesy tension | H-DOM7 |
| chromatic passing color | H-DIM, H-AUG |
| rich / colorful / chromatic harmony | H-PALETTE |
| harmony that keeps moving | H-RHYTHM |
| strong resolution / cadential pull | H-FOURTHS |
| singable / smooth line | M-STEP |
| wide / soaring / virtuosic melody | M-RANGE |
| hooky / memorable | M-MOTIF |
| dramatic leap | M-GAPFILL |
| exhaling / sighing phrase ends | M-SIGH |
| dynamic build / drop / breathing arrangement | R-DENSITY |
| varied / non-mechanical rhythm | R-DURVAR |
| clear verse/chorus sections | F-SECTIONS |
| big / full chords | V-WIDE |
| powerful unison riff | V-DOUBLE |
| sweet harmonized line | V-PARALLEL |
| clear melody-over-accompaniment | V-ROLES |
| literal section repeats | F-REPRISE |
| sparse opening | F-INTRO |
| fade ending | F-OUTRO |

---

## Files in this KB
- `harmony.txt` — H-FOURTHS, H-DOM7, H-DIM, H-AUG, H-DESCBASS, H-PEDAL, H-RHYTHM, H-PALETTE
- `melody.txt` — M-SIGH, M-MOTIF, M-GAPFILL, M-STEP, M-RANGE
- `rhythm_groove.txt` — R-SYNCO, R-OSTINATO, R-ROOTPULSE, R-STRAIGHT, R-TRIPLET, R-DURVAR, R-DENSITY
- `form.txt` — F-REPRISE, F-INTRO, F-OUTRO, F-SECTIONS
- `voicing.txt` — V-ROLES, V-WIDE, V-DOUBLE (attestation-only), V-PARALLEL
- `jazz.txt` — **J-EXT, J-IIVI, J-SWING, J-BEBOP, J-COMP, J-WALK** (genre-specialized; grounded in the 28 jazz corpus songs, jazz-conditioned dosage)
- `dosage.txt` — corpus-grounded [p25·p50·p75] target bands per axis (global + genre-conditioned for
  the split axes); what the composing loop steers toward.

Source: distilled from `pattern_catalog.py` (detectors unchanged) re-grounded over the **314-song**
grammar corpus (`../grammar/`), metadata + genre labels in `../answer_key/grammar_truth.json`,
re-grounding record in `../answer_key/kb_regrounding.json` (via `../reground_kb.py`).
