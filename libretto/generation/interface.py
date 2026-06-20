"""libretto.generation — the ONE non-deterministic seam, made pluggable.

Generation (composing a grammar region/piece) is done by an LLM and is NOT reproducible.
Everything else in libretto is deterministic. A task asks a `Generator` for grammar text given
a prompt + structured context; users plug in their own model. `measure`/`render` need no Generator.
"""
from __future__ import annotations
from pathlib import Path
from typing import Protocol, runtime_checkable

PROMPTS = Path(__file__).resolve().parent / "prompts"


def load_prompt(task: str) -> str:
    """Per-task generation brief template: prompts/<task>.md (gaptask|newgen|newgen_extend|morph)."""
    return (PROMPTS / f"{task}.md").read_text(encoding="utf-8")


@runtime_checkable
class Generator(Protocol):
    """Plug in any model. Return GRAMMAR TEXT only (a full grammar block, no prose/markdown)."""
    def generate(self, prompt: str, context: dict) -> str: ...


class ClaudeGenerator:
    """Reference impl: calls Claude with adaptive thinking. Requires `anthropic` + ANTHROPIC_API_KEY.
    `model` defaults to the latest Claude. The measurement layer never touches this class."""
    def __init__(self, model: str = "claude-opus-4-8", max_tokens: int = 8000):
        self.model, self.max_tokens = model, max_tokens

    def generate(self, prompt: str, context: dict) -> str:
        import json
        import anthropic
        client = anthropic.Anthropic()
        msg = (f"{prompt}\n\n## CONTEXT (JSON)\n```json\n{json.dumps(context, indent=1)}\n```\n"
               "Return ONLY the grammar text (header + VOICES + bars). No commentary, no code fences.")
        resp = client.messages.create(
            model=self.model, max_tokens=self.max_tokens,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": msg}],
        )
        return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()


class EchoGenerator:
    """Deterministic stub for tests/dry-runs: returns context['seed_grammar'] verbatim (or '')."""
    def generate(self, prompt: str, context: dict) -> str:
        return context.get("seed_grammar", "")
