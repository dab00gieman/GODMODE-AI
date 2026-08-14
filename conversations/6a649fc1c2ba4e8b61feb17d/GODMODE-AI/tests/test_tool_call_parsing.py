"""
Tests for tool call parsing — both text-parsed [TOOL_CALL] format and
native function calling (OpenAI-compatible) parsing from API responses.

Tests:
- parse_tool_call() with various [TOOL_CALL] formats
- parse_tool_call() with ```json code block format
- parse_tool_call() with malformed/missing tool calls
- parse_native_tool_calls() with OpenAI-compatible tool_calls structure
- parse_native_tool_calls() with edge cases (missing fields, bad JSON)
- build_tools_array() generates correct OpenAI tool specs
"""

import json
import os
import sys
import unittest

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


class TestParseToolCallText(unittest.TestCase):
    """Test text-parsed [TOOL_CALL] format (fallback path)."""

    def test_standard_tool_call(self):
        from utils.skills import parse_tool_call
        text = '[TOOL_CALL]{"tool": "weather", "args": {"location": "Lagos"}}[/TOOL_CALL]'
        result = parse_tool_call(text)
        self.assertIsNotNone(result)
        self.assertEqual(result["tool"], "weather")
        self.assertEqual(result["args"]["location"], "Lagos")

    def test_tool_call_with_prose_around_it(self):
        from utils.skills import parse_tool_call
        text = (
            "Let me check the weather for you.\n\n"
            '[TOOL_CALL]{"tool": "weather", "args": {"location": "Tokyo"}}[/TOOL_CALL]\n\n'
            "I'll get that info right away."
        )
        result = parse_tool_call(text)
        self.assertIsNotNone(result)
        self.assertEqual(result["tool"], "weather")

    def test_json_code_block_format(self):
        from utils.skills import parse_tool_call
        text = '```json\n{"tool": "calculator", "args": {"expression": "2+2"}}\n```'
        result = parse_tool_call(text)
        self.assertIsNotNone(result)
        self.assertEqual(result["tool"], "calculator")

    def test_no_tool_call(self):
        from utils.skills import parse_tool_call
        text = "This is a normal response with no tool call."
        result = parse_tool_call(text)
        self.assertIsNone(result)

    def test_malformed_json(self):
        from utils.skills import parse_tool_call
        text = '[TOOL_CALL]{"tool": "weather", "args": {broken}}[/TOOL_CALL]'
        result = parse_tool_call(text)
        self.assertIsNone(result)

    def test_skill_key_instead_of_tool(self):
        from utils.skills import parse_tool_call
        text = '[TOOL_CALL]{"skill": "weather", "args": {"location": "Berlin"}}[/TOOL_CALL]'
        result = parse_tool_call(text)
        self.assertIsNotNone(result)
        self.assertEqual(result["tool"], "weather")

    def test_missing_args_defaults_to_empty(self):
        from utils.skills import parse_tool_call
        text = '[TOOL_CALL]{"tool": "get_time"}[/TOOL_CALL]'
        result = parse_tool_call(text)
        self.assertIsNotNone(result)
        self.assertEqual(result["tool"], "get_time")
        self.assertEqual(result["args"], {})

    def test_empty_text(self):
        from utils.skills import parse_tool_call
        result = parse_tool_call("")
        self.assertIsNone(result)

    def test_tool_call_with_special_chars_in_args(self):
        from utils.skills import parse_tool_call
        text = '[TOOL_CALL]{"tool": "translate", "args": {"text": "Hello, world!", "to": "fr"}}[/TOOL_CALL]'
        result = parse_tool_call(text)
        self.assertIsNotNone(result)
        self.assertEqual(result["args"]["text"], "Hello, world!")


class TestParseNativeToolCalls(unittest.TestCase):
    """Test native function calling parsing (OpenAI-compatible)."""

    def test_standard_native_tool_call(self):
        from utils.skills import parse_native_tool_calls
        message = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_abc123",
                    "type": "function",
                    "function": {
                        "name": "weather",
                        "arguments": json.dumps({"location": "Lagos"}),
                    },
                }
            ],
        }
        result = parse_native_tool_calls(message)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["tool"], "weather")
        self.assertEqual(result[0]["args"]["location"], "Lagos")

    def test_multiple_native_tool_calls(self):
        from utils.skills import parse_native_tool_calls
        message = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "web_search",
                        "arguments": json.dumps({"query": "Python tips"}),
                    },
                },
                {
                    "id": "call_2",
                    "type": "function",
                    "function": {
                        "name": "summarize",
                        "arguments": json.dumps({"text": "Long text..."}),
                    },
                },
            ],
        }
        result = parse_native_tool_calls(message)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["tool"], "web_search")
        self.assertEqual(result[1]["tool"], "summarize")

    def test_no_tool_calls_in_message(self):
        from utils.skills import parse_native_tool_calls
        message = {
            "role": "assistant",
            "content": "Here's the answer...",
        }
        result = parse_native_tool_calls(message)
        self.assertEqual(result, [])

    def test_empty_tool_calls(self):
        from utils.skills import parse_native_tool_calls
        message = {"role": "assistant", "content": "Answer", "tool_calls": []}
        result = parse_native_tool_calls(message)
        self.assertEqual(result, [])

    def test_malformed_arguments_json(self):
        from utils.skills import parse_native_tool_calls
        message = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_x",
                    "type": "function",
                    "function": {
                        "name": "weather",
                        "arguments": "not valid json{",
                    },
                }
            ],
        }
        result = parse_native_tool_calls(message)
        # Malformed JSON should result in empty args (graceful degradation)
        # The function logs the error and skips the call
        self.assertEqual(len(result), 0)

    def test_empty_arguments_string(self):
        from utils.skills import parse_native_tool_calls
        message = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_y",
                    "type": "function",
                    "function": {
                        "name": "get_time",
                        "arguments": "",
                    },
                }
            ],
        }
        result = parse_native_tool_calls(message)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["tool"], "get_time")
        self.assertEqual(result[0]["args"], {})


class TestBuildToolsArray(unittest.TestCase):
    """Test that build_tools_array() generates correct OpenAI tool specs."""

    def setUp(self):
        # Initialize skills so we have the bundled ones registered
        from utils.skills import initialize_skills
        initialize_skills()

    def test_returns_list(self):
        from utils.skills import build_tools_array
        tools = build_tools_array()
        self.assertIsInstance(tools, list)

    def test_each_tool_has_correct_structure(self):
        from utils.skills import build_tools_array
        tools = build_tools_array()
        for tool in tools:
            self.assertEqual(tool["type"], "function")
            self.assertIn("function", tool)
            func = tool["function"]
            self.assertIn("name", func)
            self.assertIn("description", func)
            self.assertIn("parameters", func)
            params = func["parameters"]
            self.assertEqual(params["type"], "object")
            self.assertIn("properties", params)
            self.assertIn("required", params)

    def test_includes_known_skills(self):
        from utils.skills import build_tools_array
        tools = build_tools_array()
        tool_names = [t["function"]["name"] for t in tools]
        # Should include at least some bundled skills
        self.assertIn("calculator", tool_names)
        self.assertIn("weather", tool_names)


if __name__ == "__main__":
    unittest.main()
