"""Tests for the newgen retrieval-ablation harness (AXIS 1)."""
from libretto.tasks.newgen import retrieval_ablation as RA


def test_on_has_retrieval_off_does_not():
    on, off = RA.prompts("jazz", 0)
    assert "KB CONCEPTS" in on and "KB CONCEPTS" not in off        # ON injects the retrieval block, OFF strips it
    assert RA._OFF_NOTE in off
    assert len(off) < len(on)                                       # OFF is the shorter, bands-only prompt


def test_seed_varies_exemplars():
    assert RA.prompts("jazz", 0)[0] != RA.prompts("jazz", 1)[0]     # different seed -> different exemplars shown


def test_report_empty_and_aggregation():
    # empty
    r0 = RA.report(rows=[])
    assert r0["n"] == 0 and r0["on"]["n"] == 0
    # a tiny synthetic accumulation: paired genre with ON pass, OFF fail
    rows = [dict(genre="jazz", seed=0, cond="on", valid=True, pas=True),
            dict(genre="jazz", seed=0, cond="off", valid=True, pas=False)]
    r = RA.report(rows=rows)
    assert r["on"]["k"] == 1 and r["off"]["k"] == 0
    assert r["paired"]["n"] == 1 and r["paired"]["mean_on_minus_off"] == 1.0
