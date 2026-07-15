#!/usr/bin/env python3
"""generator.py — ClaudeCodeGenerator: a `libretto.generation` Generator backed by the Claude Code CLI
(`claude -p`, headless), NOT the Anthropic API. Same auth/launch pattern as axis_evolve's proposer.

Each call is ONE completion: prompt in -> the agent writes the grammar to a file -> return it. NOT a
Read/Edit/verify agent loop (that was slower and, re-sending the whole draft each turn, not cheaper).

TOKEN-EFFICIENT ITERATION via session continuation:
  start(prompt)            -> {text, session, dir, out}   round 1: fresh session (--output-format json
                                                          gives us the session id).
  resume(handle, message)  -> {text, session, dir, out}   later rounds: `claude -p --resume <session>` —
                                                          the system prompt, exemplars and the draft it
                                                          already wrote STAY in the session; only `message`
                                                          (the ranked feedback, ~200 tok) is new input,
                                                          instead of re-sending ~18-22K tokens per round.
                                                          Zero quality loss (same feedback, same rounds;
                                                          the model even keeps full memory of its draft).

Robust to throttling: `claude -p` exits ~instantly writing nothing on a 429 -> we retry with backoff.
rc==0-but-empty (cheap-model tool miss, not rate-limiting) -> retry fast.
"""
import json
import os
import random
import subprocess
import tempfile
import time
from pathlib import Path

PROJ = Path(__file__).resolve().parents[4]     # repo root (subprocess cwd + --add-dir base)
_WRITE = ("\n\n## OUTPUT — do this and NOTHING else\n"
          "Write ONLY the grammar (header line + VOICES line + bars) to this file: `{out}` (overwrite it).\n"
          "Do NOT read, list, search, or explore any other files or directories — you already have "
          "everything you need in this prompt. Do NOT run commands or create other files. Compose from the "
          "prompt directly and write the one file. No prose, no code fences.")


def _strip_fences(text: str) -> str:
    if text.startswith("```"):
        text = "\n".join(l for l in text.splitlines() if not l.strip().startswith("```"))
    return text.strip()


class ClaudeCodeGenerator:
    """Return GRAMMAR TEXT only. Auth comes from the mounted claude-code creds (no ANTHROPIC_API_KEY)."""

    # A hung call is killed at timeout_s, but a call that COMPLETES returns immediately regardless of the
    # value — so a generous timeout costs nothing on the normal (~285-366s Opus) path. Opus is SLOW, not
    # wandering (valid composes 285-366s; revises of big drafts can need ~700-900s), and doesn't truly
    # hang, so we give it 1200s base: a slow revise finishes on the FIRST try instead of wasting a 600s
    # timeout then retrying (faster + cheaper). Haiku/Sonnet stay 240 — they finish in ~2min and their
    # failure mode is rc=0 empty-write (not timeout), so a bigger value there is pointless. Adaptive
    # doubling (in _call) still gives one 2x retry for an extreme outlier. Override via timeout_s.
    MODEL_TIMEOUT = {"opus": 1200, "sonnet": 240, "haiku": 240}
    DEFAULT_TIMEOUT = 240

    def __init__(self, model="haiku", timeout_s=None, retries=4, backoff_s=30):
        self.model = model
        self.timeout_s = timeout_s if timeout_s is not None else self.MODEL_TIMEOUT.get(model, self.DEFAULT_TIMEOUT)
        self.retries, self.backoff_s = retries, backoff_s

    def _cmd(self, prompt, d, session=None):
        cmd = ["claude", "-p", prompt]
        if session:
            cmd += ["--resume", session]
        # Restrict to ONLY the Write tool: the composer's whole job is to write ONE grammar file. Without
        # Read/Grep/Glob/Bash it CANNOT wander the mounted repo or over-explore — which is what made the
        # more agentic models (esp. Opus) burn the full timeout doing nothing and hang. Model-agnostic.
        cmd += ["--allowedTools", "Write",
                "--permission-mode", "bypassPermissions", "--add-dir", str(d), "--output-format", "json"]
        if self.model:
            cmd += ["--model", self.model]
        return cmd

    def _run(self, cmd, timeout):
        try:
            r = subprocess.run(cmd, cwd=str(PROJ), capture_output=True, text=True, timeout=timeout)
            return r.returncode, (r.stdout or ""), (r.stderr or "").strip()
        except subprocess.TimeoutExpired:
            return "timeout", "", f"TimeoutExpired after {timeout:.0f}s"   # slow/hung; caller may 2x-retry
        except Exception as e:  # noqa: BLE001
            return None, "", f"{type(e).__name__}: {e}"

    @staticmethod
    def _session_id(stdout):
        try:
            return json.loads(stdout).get("session_id")
        except Exception:  # noqa: BLE001
            return None

    def _call(self, prompt, d, out, session=None, tag="gen"):
        """One claude -p call (fresh or --resume), retry on empty. Returns (text, session_id).

        ADAPTIVE TIMEOUT: the first try uses the model's base timeout. If it TIMES OUT (the piece was just
        slow to generate — bigger MIDI sequences take longer), we give it ONE more chance at DOUBLE the
        timeout, then give up on timeouts (a piece that can't finish in 2x is a true hang, not slow gen).
        rc==0-empty (cheap-model no-write) and throttle keep their own fast/backoff retries."""
        text, sid = "", session
        timeout, doubled = float(self.timeout_s), False
        for attempt in range(self.retries + 1):
            if out.exists():                       # a stale file must never count as success
                out.unlink()
            rc, sout, serr = self._run(self._cmd(prompt, d, session), timeout)
            text = _strip_fences(out.read_text(encoding="utf-8")) if out.exists() else ""
            sid = self._session_id(sout) or sid
            if text:
                break
            if attempt >= self.retries:
                break
            if rc == "timeout":
                if not doubled:                    # one adaptive doubled chance for a slow (big) piece
                    doubled, timeout = True, timeout * 2
                    print(f"[{tag}] timeout — slow piece, one retry at 2x ({timeout:.0f}s)", flush=True)
                    continue                       # retry immediately at the doubled timeout
                print(f"[{tag}] timeout again at {timeout:.0f}s (2x) — giving up (true hang)", flush=True)
                break                              # don't keep burning doubled-timeout attempts
            # rc==0-but-empty = agent finished but didn't write the file (cheap-model miss) -> retry fast;
            # rc!=0/None (throttle/crash) -> exponential backoff + jitter.
            if rc == 0:
                wait, why = random.uniform(1, 4), "no-file(rc=0)"
            else:
                wait, why = self.backoff_s * (2 ** attempt) + random.uniform(0, self.backoff_s), f"throttle(rc={rc})"
            print(f"[{tag}] empty draft {why} attempt {attempt + 1}/{self.retries + 1}; "
                  f"wait {wait:.0f}s{(' | ' + serr[:120]) if serr else ''}", flush=True)
            time.sleep(wait)
        return text, sid

    # ---- session-based API (token-efficient iteration) -------------------------------------------
    def start(self, prompt: str, context: dict = None) -> dict:
        """Round 1: fresh session. Returns {text, session, dir, out}."""
        d = tempfile.mkdtemp(prefix="newgen_")
        out = Path(d) / "composition.txt"
        ctx = f"\n\n## CONTEXT (JSON)\n```json\n{json.dumps(context, indent=1)}\n```" if context else ""
        full = f"{prompt}{ctx}{_WRITE.format(out=out)}"
        text, sid = self._call(full, d, out, session=None, tag="gen")
        return {"text": text, "session": sid, "dir": str(d), "out": str(out)}

    def resume(self, handle: dict, message: str) -> dict:
        """Later rounds: resume the session — only `message` is new input (draft/exemplars stay in ctx)."""
        d = Path(handle["dir"])
        out = Path(handle["out"])
        msg = f"{message}{_WRITE.format(out=out)}"
        text, sid = self._call(msg, d, out, session=handle.get("session"), tag="gen-resume")
        return {"text": text, "session": sid or handle.get("session"), "dir": str(d), "out": str(out)}

    def cleanup(self, handle: dict):
        try:
            Path(handle["out"]).unlink()
            os.rmdir(handle["dir"])
        except Exception:  # noqa: BLE001
            pass

    # ---- back-compat: one-shot compose (no session reuse) ----------------------------------------
    def generate(self, prompt: str, context: dict = None) -> str:
        h = self.start(prompt, context)
        self.cleanup(h)
        return h["text"]
