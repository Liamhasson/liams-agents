"""Tests for the subscription backend and the usage limit (no network, no Claude calls)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import claude as claude_mod
from shared import usage
from shared.claude import Claude, _api_cost, _transcript


def test_crossed_thresholds():
    assert usage.crossed(10.0, 12.5, 15, 0.8) == "warn"
    assert usage.crossed(14.0, 15.2, 15, 0.8) == "limit"
    assert usage.crossed(12.5, 13.0, 15, 0.8) is None  # already warned
    assert usage.crossed(1.0, 2.0, 15, 0.8) is None


def test_api_cost_uses_list_prices_and_cache_rates():
    assert round(_api_cost(claude_mod.SONNET, 1_000_000, 100_000, 0, 0), 2) == 4.5
    assert round(_api_cost(claude_mod.HAIKU, 0, 0, 1_000_000, 0), 2) == 0.1


def test_transcript_passes_a_single_message_as_is_and_labels_a_chat():
    assert _transcript([{"role": "user", "content": "Hi"}]) == "Hi"
    t = _transcript([{"role": "assistant", "content": "Cover letter?"},
                     {"role": "user", "content": "Yes"}])
    assert "You: Cover letter?" in t and "Liam: Yes" in t and t.endswith("Return only the message text.")


def _fake_run(payload, seen):
    def run(cmd, input, capture_output, text, cwd, env, timeout):
        seen.update(cmd=cmd, env=env, input=input)
        return SimpleNamespace(stdout=json.dumps(payload), stderr="")
    return run


def test_subscription_call_never_bills_the_api_and_counts_usage():
    seen, orig = {}, claude_mod.subprocess.run
    os.environ["ANTHROPIC_API_KEY"] = "sk-test"
    payload = {"is_error": False, "structured_output": {"score": 70}, "total_cost_usd": 0.004,
               "usage": {"input_tokens": 1000, "cache_read_input_tokens": 500, "output_tokens": 200}}
    try:
        claude_mod.subprocess.run = _fake_run(payload, seen)
        c = Claude()
        assert c.json_call("system", "job text", {"type": "object"}) == {"score": 70}
    finally:
        claude_mod.subprocess.run = orig
        os.environ.pop("ANTHROPIC_API_KEY", None)
    assert "ANTHROPIC_API_KEY" not in seen["env"]
    assert {"--safe-mode", "--json-schema", "--system-prompt-file"} <= set(seen["cmd"])
    assert seen["cmd"][seen["cmd"].index("--tools") + 1] == ""
    assert (c.calls, c.input_tokens, c.output_tokens, c.cost_usd) == (1, 1500, 200, 0.004)


def test_a_token_with_line_breaks_is_joined_back_into_one_line():
    seen, orig = {}, claude_mod.subprocess.run
    os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = "sk-ant-oat01-abc\ndef \r\n"
    try:
        claude_mod.subprocess.run = _fake_run({"is_error": False, "result": "ok"}, seen)
        Claude().chat("system", [{"role": "user", "content": "hi"}])
    finally:
        claude_mod.subprocess.run = orig
        os.environ.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
    assert seen["env"]["CLAUDE_CODE_OAUTH_TOKEN"] == "sk-ant-oat01-abcdef"


def test_subscription_error_is_raised_with_the_reason():
    seen, orig = {}, claude_mod.subprocess.run
    try:
        claude_mod.subprocess.run = _fake_run({"is_error": True, "result": "usage limit reached"}, seen)
        try:
            Claude().chat("system", [{"role": "user", "content": "hi"}])
            raise AssertionError("expected an error")
        except RuntimeError as e:
            assert "usage limit reached" in str(e)
    finally:
        claude_mod.subprocess.run = orig


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} usage tests passed.")
