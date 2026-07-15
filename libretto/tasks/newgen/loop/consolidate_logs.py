#!/usr/bin/env python3
"""consolidate_logs.py — merge every composition's per-round metrics into one queryable master JSONL.

Live runs (after runlog.py) already emit timestamped JSONL to <state>/logs/. This backfills the SAME flat
schema from each comp's fitness.json (which every run writes, old and new), so ALL runs — haiku/sonnet/opus,
every seed — are uniformly queryable in one file. Timestamp = fitness.json mtime (marked source=backfill).

  python newgen_loop/consolidate_logs.py         # -> newgen_loop/metrics_master.jsonl
  # query:  jq 'select(.model=="opus" and .converged)' newgen_loop/metrics_master.jsonl
"""
import json
from datetime import datetime, timezone
from pathlib import Path

NL = Path(__file__).resolve().parents[4] / "newgen_loop"   # results dir (archive/*, metrics_master.jsonl)
FIELDS = ("round", "n_extreme", "is_target", "copy_risk", "copy_gate", "budget", "converged")


def main():
    out = []
    for arch in sorted((NL / "archive").glob("*_seed*")):
        model, seed = arch.name.rsplit("_seed", 1)
        for gdir in sorted(p for p in arch.iterdir() if p.is_dir()):
            fj = gdir / "fitness.json"
            if not fj.exists():
                continue
            ts = datetime.fromtimestamp(fj.stat().st_mtime, tz=timezone.utc).isoformat(
                timespec="seconds").replace("+00:00", "Z")
            try:
                rounds = json.loads(fj.read_text())
            except Exception:  # noqa: BLE001
                continue
            for rd in rounds:
                rec = dict(ts=ts, event="round", model=model, seed=int(seed), genre=gdir.name,
                           score=rd.get("_score"), source="backfill:fitness.json")
                rec.update({k: rd.get(k) for k in FIELDS})
                out.append(rec)
    master = NL / "metrics_master.jsonl"
    master.write_text("\n".join(json.dumps(r, default=str) for r in out) + "\n")
    print(f"{len(out)} round-records from {len({(r['model'], r['seed'], r['genre']) for r in out})} comps "
          f"-> {master}")


if __name__ == "__main__":
    main()
