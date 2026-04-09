"""
Tests that chat_completion never yields the same text content twice.

Covers all four scenarios:
1. Streaming, text-only response
2. Streaming, tool-call response
3. Non-streaming, text-only response
4. Non-streaming, tool-call response

Each test collects all yielded items and asserts that text content
appears exactly once — catching the duplication bug where content was
yielded as both a string chunk AND inside a final dict.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure app is on the path
APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parent
sys.path.insert(0, str(REPO_ROOT / "retirement-sim"))
sys.path.insert(0, str(APP_ROOT))


def _make_streaming_chunks(content: str, tool_calls=None):
    """Build mock streaming chunks matching the OpenAI SDK shape."""
    chunks = []
    # Yield content in 3-char pieces
    for i in range(0, len(content), 3):
        piece = content[i : i + 3]
        delta = MagicMock()
        delta.content = piece
        delta.tool_calls = None
        choice = MagicMock()
        choice.delta = delta
        chunk = MagicMock()
        chunk.choices = [choice]
        chunks.append(chunk)

    # Yield tool calls if any
    if tool_calls:
        for j, tc in enumerate(tool_calls):
            delta = MagicMock()
            delta.content = None
            tc_mock = MagicMock()
            tc_mock.index = j
            tc_mock.id = tc["id"]
            tc_mock.function = MagicMock()
            tc_mock.function.name = tc["name"]
            tc_mock.function.arguments = tc["arguments"]
            delta.tool_calls = [tc_mock]
            choice = MagicMock()
            choice.delta = delta
            chunk = MagicMock()
            chunk.choices = [choice]
            chunks.append(chunk)

    return chunks


def _make_nonstreaming_response(content: str, tool_calls=None):
    """Build a mock non-streaming response matching OpenAI SDK shape."""
    message = MagicMock()
    message.content = content

    if tool_calls:
        tc_mocks = []
        for tc in tool_calls:
            tc_mock = MagicMock()
            tc_mock.id = tc["id"]
            tc_mock.function = MagicMock()
            tc_mock.function.name = tc["name"]
            tc_mock.function.arguments = tc["arguments"]
            tc_mocks.append(tc_mock)
        message.tool_calls = tc_mocks
    else:
        message.tool_calls = None

    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message = message
    return response


def _collect_text_from_generator(gen) -> str:
    """Collect all text content from a chat_completion generator.

    Mimics what _process_message and _handle_tool_calls do:
    strings are concatenated, dicts with content are concatenated.
    """
    text = ""
    for item in gen:
        if isinstance(item, str):
            text += item
        elif isinstance(item, dict) and item.get("content"):
            text += item["content"]
    return text


class TestChatCompletionNoDuplication(unittest.TestCase):
    """Verify chat_completion yields text content exactly once."""

    @patch("helpers.llm_client.get_client")
    def test_streaming_text_only(self, mock_get_client):
        """Streaming text response: text should appear exactly once."""
        from helpers.llm_client import chat_completion

        expected = "What is your current annual salary?"
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_streaming_chunks(
            expected
        )
        mock_get_client.return_value = mock_client

        result = _collect_text_from_generator(
            chat_completion(
                messages=[{"role": "user", "content": "test"}],
                provider="gemini",
                api_key="test",
                stream=True,
            )
        )
        self.assertEqual(result, expected)

    @patch("helpers.llm_client.get_client")
    def test_streaming_with_tool_calls(self, mock_get_client):
        """Streaming with tool calls: text should appear exactly once."""
        from helpers.llm_client import chat_completion

        expected = "I'll set that for you."
        tool_calls = [{"id": "c1", "name": "set_input", "arguments": '{"field":"current_age","value":38}'}]
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_streaming_chunks(
            expected, tool_calls=tool_calls
        )
        mock_get_client.return_value = mock_client

        result = _collect_text_from_generator(
            chat_completion(
                messages=[{"role": "user", "content": "test"}],
                provider="gemini",
                api_key="test",
                stream=True,
            )
        )
        self.assertEqual(result, expected)

    @patch("helpers.llm_client.get_client")
    def test_nonstreaming_text_only(self, mock_get_client):
        """Non-streaming text response: text should appear exactly once."""
        from helpers.llm_client import chat_completion

        expected = "What is your current annual salary?"
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_nonstreaming_response(
            expected
        )
        mock_get_client.return_value = mock_client

        result = _collect_text_from_generator(
            chat_completion(
                messages=[{"role": "user", "content": "test"}],
                provider="gemini",
                api_key="test",
                stream=False,
            )
        )
        self.assertEqual(result, expected)

    @patch("helpers.llm_client.get_client")
    def test_nonstreaming_with_tool_calls(self, mock_get_client):
        """Non-streaming with tool calls: content should NOT be double-counted.

        When tool_calls are present, the dict contains content for the
        assistant message, but consumers should only use it for forwarding
        to the next API call — not for display text. The tool handler
        will make a follow-up call for the display text.
        """
        from helpers.llm_client import chat_completion

        tool_calls = [{"id": "c1", "name": "set_input", "arguments": '{"field":"current_age","value":38}'}]
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _make_nonstreaming_response(
            "I'll set that.", tool_calls=tool_calls
        )
        mock_get_client.return_value = mock_client

        # Collect everything the generator yields
        items = list(
            chat_completion(
                messages=[{"role": "user", "content": "test"}],
                provider="gemini",
                api_key="test",
                stream=False,
            )
        )

        # Should yield exactly ONE item: a dict with tool_calls
        self.assertEqual(len(items), 1)
        self.assertIsInstance(items[0], dict)
        self.assertIn("tool_calls", items[0])
        # No separate string yield
        string_items = [i for i in items if isinstance(i, str)]
        self.assertEqual(len(string_items), 0)


if __name__ == "__main__":
    unittest.main()
