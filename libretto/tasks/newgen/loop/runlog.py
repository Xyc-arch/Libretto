#!/usr/bin/env python3
"""runlog.py — structured, timestamped JSONL event logging for newgen_loop runs.

Industry-standard practice: every event (run_start, round, early_stop, run_end) is one JSON line with a
UTC ISO-8601 timestamp and flat metric fields (n_extreme, copy_risk, gates, converged, …), appended to a
per-run timestamped file under <state>/logs/. Thread-safe (parallel composers log concurrently). The file
is machine-queryable (jq / pandas) and never overwritten across runs.

  from libretto.tasks.newgen.loop.runlog import RunLog
  log = RunLog(state_dir, model="opus", params={...})
  log.event("round", genre="jazz", seed=1, round=2, n_extreme=4, copy_risk=0.23, converged=False)
  log.close(summary={...})
"""
import json
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path


def _utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _git_sha(proj):
    try:
        return subprocess.run(["git", "-C", str(proj), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=5).stdout.strip() or None
    except Exception:  # noqa: BLE001
        return None


class RunLog:
    """Append-only JSONL event log for one batch run. One file per run: logs/run_<UTCstamp>_<model>.jsonl."""

    def __init__(self, state_dir, model="?", params=None, proj=None):
        self._lock = threading.Lock()
        stamp = _utc_now().replace(":", "").replace("-", "").replace(".", "").rstrip("Z")
        self.run_id = stamp
        self.path = None
        self._fh = None
        # Logging must NEVER crash a composition run — if the logs dir/file isn't writable (read-only
        # mount, perms), degrade to a no-op logger and warn once instead of taking the whole run down.
        try:
            d = Path(state_dir) / "logs"
            d.mkdir(parents=True, exist_ok=True)
            self.path = d / f"run_{stamp}_{model}.jsonl"
            self._fh = self.path.open("a", encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            print(f"[runlog] disabled — could not open log ({type(e).__name__}: {e})", flush=True)
        self.event("run_start", model=model, params=params or {},
                   git_sha=_git_sha(proj or Path(state_dir).parent))

    def event(self, event, **fields):
        """Write one timestamped JSONL record. Thread-safe; flushed so a killed run keeps its logs.
        A failed write is swallowed — never let logging break the run."""
        if self._fh is None:
            return
        rec = {"ts": _utc_now(), "event": event, "run_id": self.run_id}
        rec.update(fields)
        try:
            line = json.dumps(rec, default=str)
            with self._lock:
                self._fh.write(line + "\n")
                self._fh.flush()
        except Exception:  # noqa: BLE001
            pass

    def close(self, summary=None):
        self.event("run_end", **(summary or {}))
        if self._fh is not None:
            with self._lock:
                try:
                    self._fh.close()
                except Exception:  # noqa: BLE001
                    pass
