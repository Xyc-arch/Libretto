#!/usr/bin/env python3
"""batch.py — Dockerized axis-guided composition batch, PARALLEL.

Composes N pieces (genres × seeds) concurrently — each a Claude Code agent scored on the 39-axis
system with the nontrivial feedback (classifier genre-steer + genre-conditioned p5/p95 guardrail +
musical translation + copy_risk). DISJOINT retrieval is pre-assigned across all jobs up front (a shared
`used` set), so parallel workers never share an exemplar. `--parallel` composer agents run at once.

    python -m newgen_loop.batch --seeds 3 --parallel 11 --rounds 3          # all 11 genres × 3 = 33 pieces
    python -m newgen_loop.batch --genres jazz,metal --seeds 2 --parallel 4
"""
import argparse
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import median

PROJ = Path(__file__).resolve().parents[4]     # repo root (…/libretto/tasks/newgen/loop/batch.py)
sys.path.insert(0, str(PROJ))

from libretto.tasks.newgen import retrieval as R                          # noqa: E402
from libretto.core.understanding_probe import Song                        # noqa: E402
from libretto.tasks.newgen.loop.generator import ClaudeCodeGenerator      # noqa: E402
from libretto.tasks.newgen.loop.feedback import compose_feedback, GENRES  # noqa: E402
from libretto.tasks.newgen.loop.runlog import RunLog                      # noqa: E402
import libretto                                                           # noqa: E402

GRAMMAR = libretto.data_root() / "grammar"
# results (state/archive/mp3s) live at the deploy dir newgen_loop/, NOT in the package; the container sets
# NEWGEN_STATE=/state (mounted). Local default -> repo-root newgen_loop/state.
STATE = Path(os.environ.get("NEWGEN_STATE") or (PROJ / "newgen_loop" / "state"))
BRIEF = (Path(__file__).resolve().parent / "composer_brief.md").read_text(encoding="utf-8")
# For the retrieval-OFF ablation, drop the "## Use the STYLE REFERENCE (retrieved real exemplars)" section
# (there are none) and replace it with a NEUTRAL instruction — so OFF never references real songs or is told a
# specific instrumentation; it just picks a genre-appropriate arrangement itself. Keeps the sections BEFORE it
# (grammar format) and AFTER it (feedback loop). ON keeps the full brief.
def _brief_no_retrieval(brief):
    mark = "## Use the STYLE REFERENCE"
    if mark not in brief:
        return brief
    before = brief.split(mark)[0].rstrip()
    after = brief.split(mark, 1)[1]
    m = re.search(r"\n## ", after)                    # the next "## …" section (feedback loop) — keep it
    rest = after[m.start():].lstrip("\n") if m else ""
    neutral = ("## NO REFERENCE PROVIDED (compose from your own knowledge)\n"
               "You are given NO exemplars or reference material — only the target genre name. Choose a "
               "genre-appropriate arrangement and instrumentation YOURSELF from the GM palette (bass + harmony "
               "+ melody + drums as fits the genre), and compose original material purely from your own "
               "knowledge of the target genre.\n")
    return f"{before}\n\n{neutral}\n{rest}"


BRIEF_NORETR = _brief_no_retrieval(BRIEF)
LOG = None   # set in main() to a RunLog; every round's metrics are appended as a timestamped JSONL event


def _exemplar_bars(ex_ids):
    ns = [Song(GRAMMAR / f"{s}.txt").n_bars for s in ex_ids if (GRAMMAR / f"{s}.txt").exists()]
    return int(median(ns)) if ns else 96


def _completed(genre, s):
    """Return a manifest entry if this comp already has a real (parseable) best; else None. Used by
    --resume so a rate-limited re-run keeps the good comps and only redoes the empty/failed ones."""
    wd = STATE / genre / f"seed_{s}"
    bt = wd / "best.txt"
    if not (bt.exists() and bt.stat().st_size > 0):
        return None
    try:
        fit = json.loads((wd / "fitness.json").read_text())
        real = [r for r in fit if r.get("n_extreme") != 99]              # drop throttled/unparseable rounds
        ex = json.loads((wd / "exemplars.json").read_text())["exemplar_ids"]
    except Exception:  # noqa: BLE001
        return None
    if not real:
        return None
    best = min(real, key=lambda r: r["_score"])
    return dict(genre=genre, seed=s, exemplars=ex, converged=bool(best.get("converged")),
                best_round=best.get("round"), score=best.get("_score"), reads_as=best.get("reads_as"))


def _run_one(job, gen, rounds, target_bars, good_ext=-1, patience=1):
    """One composition: greedy hill-climb. Round 1 composes from the exemplars; every later round REVISES
    the best draft so far IN PLACE (keep what works, fix only the flagged axes) using that best draft's
    own feedback — so iteration climbs instead of random-walking.

    ROI early-stops (token-waste reduction): stop once a draft is `good_enough` (on-target, ≤good_ext
    extremes) even short of strict convergence, and stop after `patience` revise rounds fail to beat the
    incumbent best (~half of revise rounds don't improve it — those are pure wasted tokens)."""
    genre, s, ret = job
    ex_ids = ret["exemplar_ids"]
    wd = STATE / genre / f"seed_{s}"; wd.mkdir(parents=True, exist_ok=True)
    (wd / "exemplars.json").write_text(json.dumps(ret, indent=2, default=str))  # persist EARLY so an
    # interrupted run can resume with the SAME exemplars (see main()'s --resume disk reuse)
    exbars = (f"(the retrieved exemplars run ~{_exemplar_bars(ex_ids)} bars.)" if ex_ids else "")
    brief = BRIEF if ex_ids else BRIEF_NORETR          # OFF gets the neutral, no-real-song brief
    style = (f"{brief}\n\n## TARGET GENRE: {genre}\n"
             f"## TARGET LENGTH: ~{target_bars} bars — a FULL piece of this length with real sections "
             f"(intro/theme/development), NOT a short fragment. {exbars}\n\n{ret['text']}")
    rounds_log, best = [], None

    def _sel_key(rd):
        """Ranking for picking `best` (lower is better): (1) NOVELTY — a draft over its genre copy gate
        loses to any draft under it; (2) reads-as-target; (3) fewer extreme axes; (4) less copy."""
        gate = rd.get("copy_gate", 0.35)
        return (rd["copy_risk"] > gate, 0 if rd["is_target"] else 1, rd["n_extreme"], rd["copy_risk"])

    def score_and_log(p, r):
        """Score a draft on the 39-axis system and fold it into rounds_log/best. Local + free — NO
        claude -p tokens — which is exactly why resume can re-score existing drafts for nothing."""
        nonlocal best
        try:
            fb, converged, info = compose_feedback(p, genre)
        except Exception as e:  # noqa: BLE001
            fb, converged, info = [f"(draft unparseable: {e})"], False, dict(reads_as="?", is_target=False, n_extreme=99, copy_risk=1.0)
        gate = info.get("copy_gate", 0.35)
        sc = (0 if info["is_target"] else 100) + info["n_extreme"] + (5 if info["copy_risk"] > gate else 0)
        rd = dict(round=r, path=str(p), converged=converged, feedback=fb, _score=sc, **info)
        rounds_log.append(rd)
        (wd / f"round_{r}_feedback.txt").write_text("\n".join(fb), encoding="utf-8")
        if LOG:                                            # timestamped structured metrics record
            LOG.event("round", genre=genre, seed=s, round=r, score=sc,
                      **{k: v for k, v in info.items() if k != "reads_as"})
        # NOVELTY-CONTROLLED selection: a draft over its genre copy gate can NEVER be picked as best while
        # a novel draft exists (novelty-pass is the first key), then prefer on-target, fewer extremes, less
        # copy. With the calibrated gate most drafts pass, so this reduces to (genre, extremes) as before —
        # it only bites when a round is a near-copy.
        if info["n_extreme"] != 99 and (best is None or _sel_key(rd) < _sel_key(best)):
            best = rd
        return rd

    def good_enough(rd):
        """Stop early once a draft is DECENT — on-target and within the genre's NORMAL extreme range
        (p75 of real songs), even if copy_risk hasn't cleared and it's short of the stricter convergence
        bar (median). Grinding expensive full-rewrite revise rounds to shave the last extreme off an
        already-in-range piece is poor ROI. --good-ext >=0 overrides with a flat cap."""
        bar = good_ext if good_ext >= 0 else rd.get("budget_stop", rd.get("budget", 3))
        return rd["is_target"] and rd["n_extreme"] <= bar

    # ---- RESUME: re-score drafts already on disk from an interrupted run (free), continue after them ----
    start_round, done = 1, False
    for r in range(1, rounds + 1):
        p = wd / f"c_r{r}.txt"
        if not (p.exists() and p.stat().st_size > 0):
            break
        rd = score_and_log(p, r)
        if rd["n_extreme"] == 99:                          # a partial/corrupt draft — redo this round
            rounds_log.pop(); break
        start_round = r + 1
        if rd["converged"] or good_enough(rd):
            done = True; break
    if start_round > 1:
        print(f"[{genre} s{s}] resumed: re-scored {start_round - 1} existing round(s), "
              f"best extremes {best['n_extreme'] if best else '?'}", flush=True)

    # ---- compose (round 1) / refine (later rounds) from where we left off ----
    # `handle` is the LIVE claude -p session for this composition. When it exists, a revise round resumes
    # it and sends ONLY the feedback (~200 tok) — the system prompt, exemplars and the draft the model
    # already wrote stay in the session, instead of re-sending ~18-22K tokens. Cold paths (round 1, or the
    # first revise after a cross-process disk-resume) start a fresh session carrying the needed context.
    handle, session_has_best, no_improve = None, False, 0
    revise_hdr = (f"## REFINE — keep its {genre} feel, arrangement, sections and every axis already in "
                  f"range; change ONLY what's flagged (touching an in-range part just relocates the "
                  f"problem). Rewrite the full grammar with those targeted changes.\n\n"
                  f"### ISSUES TO FIX (act on these, leave the rest alone)\n")
    # if the resumed disk best is already good enough, don't start any new rounds
    if best is not None and (best.get("converged") or good_enough(best)):
        done = True
    for r in (range(0) if done else range(start_round, rounds + 1)):
        fb_txt = "\n".join(best["feedback"]) if best else ""
        was_revise = best is not None
        if best is None:                                   # round 1: fresh compose from the exemplars
            handle = gen.start(style)
        elif handle is not None and session_has_best:      # WARM: session's latest draft IS the best —
            handle = gen.resume(handle, revise_hdr + fb_txt)  # send ONLY feedback (~200 tok)
        else:                                              # cold revise: latest≠best (regression) or disk-
            if handle is not None:                         # resumed — carry the BEST draft explicitly once
                gen.cleanup(handle)
            cur = Path(best["path"]).read_text(encoding="utf-8")
            handle = gen.start(f"{style}\n\n{revise_hdr}### CURRENT DRAFT\n{cur}\n\n{fb_txt}")
        grammar = handle["text"]
        p = wd / f"c_r{r}.txt"; p.write_text(grammar, encoding="utf-8")
        rd = score_and_log(p, r)
        improved = best is not None and best["round"] == r  # did THIS round become the new best?
        session_has_best = improved
        no_improve = 0 if (improved or not was_revise) else no_improve + 1
        print(f"[{genre} s{s}] round {r}: {rd['reads_as']} | extremes {rd['n_extreme']} "
              f"| copy {rd['copy_risk']:.2f}{' | CONVERGED' if rd['converged'] else ''}"
              f"{'' if improved or not was_revise else ' | no-improve'}", flush=True)
        if rd["converged"] or good_enough(rd):
            break
        if patience and no_improve >= patience:            # a revise round didn't beat the incumbent — stop
            print(f"[{genre} s{s}] early-stop: {no_improve} revise round(s) w/o improvement "
                  f"(keeping best r{best['round'] if best else '?'})", flush=True)
            if LOG:
                LOG.event("early_stop", genre=genre, seed=s, reason="no_improvement",
                          kept_round=(best or {}).get("round"))
            break
    if handle:
        gen.cleanup(handle)
    novel = bool(best and best["copy_risk"] <= best.get("copy_gate", 0.35))
    if best and LOG:                                       # the picked-best summary for this composition
        LOG.event("best", genre=genre, seed=s, best_round=best["round"], score=best["_score"],
                  n_extreme=best["n_extreme"], is_target=best["is_target"], copy_risk=best["copy_risk"],
                  converged=best["converged"], novel=novel, n_rounds=len(rounds_log))
    if best:
        (wd / "best.txt").write_text(Path(best["path"]).read_text(encoding="utf-8"), encoding="utf-8")
        (wd / "fitness.json").write_text(json.dumps(
            [{k: v for k, v in rd.items() if k != "feedback"} for rd in rounds_log], indent=2, default=str))
        if not novel:                                      # every draft was a near-copy — surface it
            print(f"[{genre} s{s}] ⚠ picked best copy_risk {best['copy_risk']:.2f} > gate "
                  f"{best.get('copy_gate', 0.35):.2f} — no novel draft this run", flush=True)
    (wd / "exemplars.json").write_text(json.dumps(ret, indent=2, default=str))
    return dict(genre=genre, seed=s, exemplars=ex_ids, converged=bool(best and best["converged"]),
                best_round=(best or {}).get("round"), score=(best or {}).get("_score"),
                reads_as=(best or {}).get("reads_as"),
                copy_risk=(best or {}).get("copy_risk"), novel=novel)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--genres", default="", help="comma-separated; empty = all 11 genres")
    ap.add_argument("--seeds", type=int, default=3, help="compositions per genre (this batch)")
    ap.add_argument("--seed-start", type=int, default=0,
                    help="first seed index for this batch (run seeds [seed_start, seed_start+seeds)). Lets "
                         "you run seed 1 then seed 2 as separate batches while staying disjoint from prior seeds")
    ap.add_argument("--k", type=int, default=3, help="retrieved exemplars per seed")
    ap.add_argument("--no-retrieval", action="store_true",
                    help="ABLATION: compose from the genre NAME only (no KB concepts / no exemplars)")
    ap.add_argument("--rounds", type=int, default=3, help="max iterations (round 1 compose + up to 2 revises)")
    ap.add_argument("--parallel", type=int, default=11, help="concurrent composer agents")
    ap.add_argument("--target-bars", type=int, default=75)
    ap.add_argument("--good-ext", type=int, default=-1,
                    help="flat cap: stop refining once on-target with <= this many extreme axes. Default -1 "
                         "= use the genre's real-corpus extreme budget (a typical real song of the genre)")
    ap.add_argument("--patience", type=int, default=1,
                    help="stop after this many revise rounds fail to beat the incumbent best (0 = never "
                         "early-stop on no-improvement)")
    ap.add_argument("--timeout", type=int, default=0,
                    help="override the per-call base timeout (s); 0 = model default (opus 600, else 240). "
                         "A timed-out call still gets one adaptive 2x retry.")
    ap.add_argument("--model", default="haiku",
                    help="composer model — default haiku (~15x cheaper, no rate-window throttle); "
                         "pass --model opus for higher quality")
    ap.add_argument("--resume", action="store_true",
                    help="keep comps that already have a valid (parseable) best.txt; only run failed/missing")
    a = ap.parse_args()
    genres = [g.strip() for g in a.genres.split(",") if g.strip()] or sorted(GENRES)
    STATE.mkdir(parents=True, exist_ok=True)

    # ---- pre-assign DISJOINT exemplars for every job (before parallel launch) ----
    # In --resume, a comp already holding a real (non-sentinel) best is KEPT; its exemplars are reserved
    # so the re-run jobs stay disjoint from the completed ones. Also seed `used` from ALL existing seeds'
    # exemplars on disk (state + archive) so a later batch (e.g. seed 1/2) stays disjoint from earlier ones.
    used, jobs, kept, resumed = set(), [], [], 0
    seeds = range(a.seed_start, a.seed_start + a.seeds)
    # exclude exemplars already used by OTHER seeds of THIS run in state/ (so seed 1/2 stay disjoint from
    # seed 0 and each other). Only seeds NOT in this batch — a resumed comp reuses its own via the exj branch.
    for exj in STATE.glob("*/seed_*/exemplars.json"):
        s_existing = int(exj.parent.name.split("_")[1])
        if s_existing not in seeds:
            try:
                used |= set(json.loads(exj.read_text()).get("exemplar_ids", []))
            except Exception:  # noqa: BLE001
                pass
    for genre in genres:
        for s in seeds:
            done = _completed(genre, s) if a.resume else None
            if done:
                kept.append(done); used |= set(done["exemplars"]); continue
            exj = STATE / genre / f"seed_{s}" / "exemplars.json"
            if a.resume and exj.exists():                  # interrupted comp — reuse its SAME exemplars
                ret = json.loads(exj.read_text()); resumed += 1
            elif a.no_retrieval:
                # ABLATION (retrieval OFF): compose from the genre NAME only — no KB concepts, no exemplars.
                ret = {"genre": genre, "concept_ids": [], "exemplar_ids": [], "text": ""}
            else:
                try:
                    ret = R.build_retrieval(genre, k_exemplars=a.k, exclude=used, seed=1000 + s)
                except Exception as e:  # noqa: BLE001
                    print(f"[skip] {genre} seed {s}: {e}", flush=True); continue
            used |= set(ret["exemplar_ids"])
            jobs.append((genre, s, ret))
    print(f"{len(jobs)} to run"
          + (f" ({resumed} resuming from disk)" if resumed else "")
          + (f" (+{len(kept)} kept)" if kept else "")
          + f" | {a.parallel} parallel agents | rounds<= {a.rounds} | disjoint pool used {len(used)}", flush=True)

    # ---- structured timestamped metrics log (JSONL, per run) ----
    global LOG
    LOG = RunLog(STATE, model=a.model, proj=PROJ, params=dict(
        genres=genres, seeds=list(seeds), k=a.k, rounds=a.rounds, parallel=a.parallel,
        target_bars=a.target_bars, good_ext=a.good_ext, patience=a.patience,
        timeout=(a.timeout or "model-default"), resume=a.resume, n_jobs=len(jobs), n_kept=len(kept)))
    print(f"[log] metrics -> {LOG.path}", flush=True)

    # ---- run concurrently (each worker blocks on its own claude -p) ----
    gen = ClaudeCodeGenerator(model=a.model, timeout_s=(a.timeout or None))   # stateless; own temp dir/call
    manifest = list(kept)
    with ThreadPoolExecutor(max_workers=a.parallel) as pool:
        for m in pool.map(lambda j: _run_one(j, gen, a.rounds, a.target_bars, a.good_ext, a.patience), jobs):
            manifest.append(m)

    all_ex = [e for m in manifest for e in m["exemplars"]]
    disjoint = len(all_ex) == len(set(all_ex))
    conv = sum(m["converged"] for m in manifest)
    novel = sum(1 for m in manifest if m.get("novel", True))
    (STATE / "batch_manifest.json").write_text(json.dumps(
        {"disjoint_retrieval": disjoint, "n_compositions": len(manifest),
         "converged": conv, "runs": manifest}, indent=2))
    LOG.close(summary=dict(n_compositions=len(manifest), converged=conv, novel=novel,
                           disjoint=disjoint, on_target=sum(1 for m in manifest if (m.get("score") or 999) < 100)))
    print(f"\nDONE: {len(manifest)} compositions | converged {conv}/{len(manifest)} | "
          f"disjoint {disjoint} -> {STATE}\n[log] metrics saved -> {LOG.path}")


if __name__ == "__main__":
    main()
