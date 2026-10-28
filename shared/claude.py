"""Claude wrapper.

Haiku for cheap classification/scoring; forces strict JSON via tool-use so the
model can't drift from the schema. Tracks token usage for cost visibility
(BUILD_BRIEF §15).
"""

from __future__ import annotations

from typing import Any, Optional

import anthropic

from . import config

HAIKU = "claude-haiku-4-5-20251001"
SONNET = "claude-sonnet-4-6"


class Claude:
    def __init__(self, model: str = HAIKU):
        self.client = anthropic.Anthropic(api_key=config.require("ANTHROPIC_API_KEY"))
        self.model = model
        self.input_tokens = 0
        self.output_tokens = 0

    def json_call(self, system: str, user: str, schema: dict,
                  tool_name: str = "submit", max_tokens: int = 1024,
                  temperature: Optional[float] = None) -> dict[str, Any]:
        """Return the model's structured output as a dict matching `schema`."""
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
        self.input_tokens += resp.usage.input_tokens
        self.output_tokens += resp.usage.output_tokens
        for block in resp.content:
            if block.type == "tool_use":
                return block.input
        raise RuntimeError("Claude returned no structured output")

    def chat(self, system: str, messages: list[dict], max_tokens: int = 800,
             temperature: Optional[float] = None) -> str:
        """Free-text turn (for the Writer's conversation)."""
        kwargs = {} if temperature is None else {"temperature": temperature}
        resp = self.client.messages.create(
            model=self.model, max_tokens=max_tokens, system=system, messages=messages, **kwargs,
        )
        self.input_tokens += resp.usage.input_tokens
        self.output_tokens += resp.usage.output_tokens
        return "".join(b.text for b in resp.content if b.type == "text").strip()

    def cost_summary(self) -> str:
        return (f"tokens: {self.input_tokens} in / {self.output_tokens} out "
                f"({self.model})")
