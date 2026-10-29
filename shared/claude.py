"""Claude wrapper.

Two backends, same interface:
- "subscription" (default): runs each call through the Claude Code CLI
  (`claude -p`) on Liam's Claude subscription, so the agents cost nothing extra.
  Locally it uses his Claude Code login; on GitHub it uses CLAUDE_CODE_OAUTH_TOKEN
  (made with `claude setup-token`). Customisations, tools and CLAUDE.md are off,
  so each call sees only the prompt we send.
- "api": the Anthropic API with ANTHROPIC_API_KEY, billed per token.
  Set CLAUDE_BACKEND=api to use it.

Haiku for cheap classification/scoring; strict JSON via a schema so the model
can't drift. Tracks tokens and the API-equivalent cost for the usage log
(BUILD_BRIEF §15).
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from typing import Any, Optional

from . import config

HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"

# API list prices per million tokens (input, output). Cache reads 0.1x, 5-min writes 1.25x.
PRICES = {HAIKU: (1.0, 5.0), SONNET: (3.0, 15.0)}

CLI_TIMEOUT = 600  # seconds per call


def backend() -> str:
    return os.environ.get("CLAUDE_BACKEND", "subscription").strip().lower()


def _api_cost(model: str, inp: int, out: int, cache_read: int, cache_write: int) -> float:
    pin, pout = PRICES.get(model, PRICES[SONNET])
    return (inp * pin + out * pout + cache_read * pin * 0.1 + cache_write * pin * 1.25) / 1_000_000


class Claude:
    def __init__(self, model: str = HAIKU):
        self.model = model
        self.backend = backend()
        self.client = None
        if self.backend == "api":
            import anthropic
            self.client = anthropic.Anthropic(api_key=config.require("ANTHROPIC_API_KEY"))
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.cost_usd = 0.0  # what these calls cost, or would cost, on the API

    # ---- public interface ---------------------------------------------------
    def json_call(self, system: str, user: str, schema: dict,
                  tool_name: str = "submit", max_tokens: int = 1024,
                  temperature: Optional[float] = None) -> dict[str, Any]:
        """Return the model's structured output as a dict matching `schema`."""
        if self.backend != "api":
            data = self._cli(system, user, schema)
            if not isinstance(data.get("structured_output"), dict):
                # Without the API's forced tool call the model can decline when input is thin.
                data = self._cli(system, user + "\n\nAlways return the structured result, even when "
                                 "information is missing: use your best judgement and name the gaps in "
                                 "the fields.", schema)
            if not isinstance(data.get("structured_output"), dict):
                raise RuntimeError(f"Claude returned no structured output: {str(data.get('result'))[:300]}")
            return data["structured_output"]
        kwargs = {} if temperature is None else {"temperature": temperature}
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            tools=[{
                "name": tool_name,
                "description": "Return the structured result.",
                "input_schema": schema,
            }],
            tool_choice={"type": "tool", "name": tool_name},
            **kwargs,
        )
        self._count_api(resp.usage)
        for block in resp.content:
            if block.type == "tool_use":
                return block.input
        raise RuntimeError("Claude returned no structured output")

    def chat(self, system: str, messages: list[dict], max_tokens: int = 800,
             temperature: Optional[float] = None) -> str:
        """Free-text turn (for the Writer's conversation)."""
        if self.backend != "api":
            return str(self._cli(system, _transcript(messages)).get("result", "")).strip()
        kwargs = {} if temperature is None else {"temperature": temperature}
        resp = self.client.messages.create(
            model=self.model, max_tokens=max_tokens, system=system, messages=messages, **kwargs,
        )
        self._count_api(resp.usage)
        return "".join(b.text for b in resp.content if b.type == "text").strip()

    def cost_summary(self) -> str:
        label = "API-equivalent, paid by subscription" if self.backend != "api" else "API"
        return (f"{self.calls} calls, tokens: {self.input_tokens} in / {self.output_tokens} out, "
                f"${self.cost_usd:.3f} {label} ({self.model})")

    # ---- backends -----------------------------------------------------------
    def _count_api(self, usage) -> None:
        read = getattr(usage, "cache_read_input_tokens", 0) or 0
        write = getattr(usage, "cache_creation_input_tokens", 0) or 0
        self.calls += 1
        self.input_tokens += usage.input_tokens + read + write
        self.output_tokens += usage.output_tokens
        self.cost_usd += _api_cost(self.model, usage.input_tokens, usage.output_tokens, read, write)

    def _cli(self, system: str, prompt: str, schema: Optional[dict] = None) -> dict:
        """One `claude -p` call on the subscription. No tools, no customisations, no history."""
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}  # never bill the API here
        with tempfile.TemporaryDirectory() as tmp:
            sys_path = os.path.join(tmp, "system.txt")
            with open(sys_path, "w") as f:
                f.write(system)
            # Thinking off: same behaviour as the API calls the agents were tuned on, at a
            # quarter of the tokens and a fifth of the time.
            cmd = ["claude", "-p", "--safe-mode", "--tools", "", "--strict-mcp-config",
                   "--no-session-persistence", "--model", self.model,
                   "--settings", json.dumps({"alwaysThinkingEnabled": False}),
                   "--system-prompt-file", sys_path, "--output-format", "json"]
            if schema is not None:
                cmd += ["--json-schema", json.dumps(schema)]
            proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                                  cwd=tmp, env=env, timeout=CLI_TIMEOUT)
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            raise RuntimeError(f"Claude Code failed: {(proc.stdout or proc.stderr)[:300]}")
        usage = data.get("usage") or {}
        self.calls += 1
        self.input_tokens += sum(usage.get(k, 0) or 0 for k in
                                 ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
        self.output_tokens += usage.get("output_tokens", 0) or 0
        self.cost_usd += data.get("total_cost_usd", 0) or 0
        if data.get("is_error"):
            raise RuntimeError(f"Claude Code error: {str(data.get('result'))[:300]}")
        return data


def _transcript(messages: list[dict]) -> str:
    """The CLI takes one prompt, so a multi-turn chat is passed as a transcript."""
    if len(messages) == 1:
        return messages[0]["content"]
    lines = [f"{'Liam' if m['role'] == 'user' else 'You'}: {m['content']}" for m in messages]
    return ("Our conversation so far:\n\n" + "\n\n".join(lines)
            + "\n\nWrite your next message to Liam, replying to his last message. "
              "Return only the message text.")
