"""education — generate single-channel-piano practice pieces for music learners.

Pipeline: browse kb_theory for the concepts a learner's required challenge names (retrieval.py) ->
build a practice-piece prompt at a level (setup.py) -> generate single-voice piano -> verify the challenge
is actually present AND the piece is novel/not copied (measure.py) -> render score + MIDI.
"""
