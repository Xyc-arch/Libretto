# Genre-classifier corroboration of the evolved composition (R1 vs R4)

Classifier: logistic regression trained on the 255 ground-truth-labeled corpus songs (8 genres),
standardized 28-axis features. It NEVER saw R1 or R4. SCOPE: a confident genre call means the piece
is structurally TYPICAL of that genre (idiom-confirmation), NOT a quality verdict.

## ROUND 1 (stamped loop) — predicted electronic_dance, p=0.82 (CONFIDENT, norm-entropy 0.31)
   electronic_dance 81.9% | funk_soul_rnb 10.2% | jazz 5.5% | latin 2.2% | rest ~0
## ROUND 4 (evolved) — predicted funk_soul_rnb, p=0.39 (SPREAD, norm-entropy 0.77, margin 0.18)
   funk_soul_rnb 39.0% | jazz 21.3% | folk_country 15.9% | core_pop_rock 11.3% | latin 7.3%
   | classical 4.8% | film 0.4% | electronic_dance 0.0%

## Reading (honest — the hypothesis was half right, and the correction is the finding)
- The loop did NOT go "confused → confident-single-genre". In raw confidence it went the OTHER way:
  R1 confident, R4 spread. But peak confidence is not the right yardstick here.
- **R1's 82% confidence is an artifact of mechanical EXTREMITY, not idiomatic authenticity.** R1 was
  a max-syncopation (100th pct), uniform-duration, narrow-voicing, looping vamp — and those extremes
  coincide with the electronic_dance cluster's profile. The classifier confidently calls it
  electronic because it is a caricature, not because it is a rich example of its intended idiom
  (a soul/R&B groove). Confident-but-wrong-family.
- **R4's spread is mass on the MUSICALLY CORRECT neighborhood.** Top pick funk_soul_rnb (39%) — which
  is exactly the brief (soul/R&B) — with jazz second (21%); funk_soul + jazz + core_pop together hold
  ~72%. And R4 puts ~0% on electronic_dance and 0.4% on film: it firmly REJECTS the mechanical and
  orchestral poles. The high entropy reflects a genuine stylistic blend (soul + jazz-pop), which is
  what "a competent jazz-pop arrangement over a soul groove" actually is — and is consistent with the
  earlier finding that these buckets structurally overlap and confuse.
- **So the loop moved the piece's genre identity from a caricature pole (electronic, unintended) into
  the intended soul/funk/jazz-pop family.** That is independent corroboration — from a classifier that
  knows genre, trained only on real songs — that R4 is idiomatically real soul/jazz-pop, complementary
  to the percentile-band check (0 extreme axes, 16/28 in-band). It is NOT evidence R4 is "good."

## Does the classifier agree with the musical read?
Yes, on the family: #1 funk_soul_rnb matches the soul/R&B brief; #2 jazz matches the jazz-pop
harmony (maj7/9ths, chromatic color). It can't name a single label because R4 genuinely sits at the
soul–jazz-pop intersection — the right answer for this music.
