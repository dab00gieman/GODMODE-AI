"""
Tests for reflect_on_task() — the learning loop's reflection phase.

Tests:
- JSON parsing of the LLM's reflection response
- Skill creation decision logic (should_learn = True/False)
- Skill name, description, triggers extraction
- Malformed reflection response handling
- Mocked send_message to avoid real API calls
"""

import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


class TestReflectOnTask(unittest.TestCase):
    """Test the reflection logic without making real API calls."""

    def _make_tool_history(self):
        """Create a sample tool history for testing."""
        return [
            {
                "tool": "web_search",
                "args": {"query": "Python asyncio tutorial"},
                "result": "Python asyncio is a library for writing concurrent code...",
                "iteration": 1,
            },
            {
                "tool": "summarize",
                "args": {"text": "Python asyncio is..."},
                "result": "Summary: asyncio enables async programming in Python",
                "iteration": 2,
            },
        ]

    @patch('utils.skills.create_learned_skill')
    @patch('utils.openrouter.send_message')
    def test_reflection_parses_should_learn_true(self, mock_send, mock_create):
        """Test that reflect_on_task correctly parses a 'should_learn: true' response."""
        from utils.reflector import reflect_on_task

        mock_response = json.dumps({
            "should_learn": True,
            "skill_name": "python_async_search",
            "description": "Search for Python asyncio tutorials and summarize them",
            "triggers": ["python asyncio", "async tutorial", "asyncio guide"],
            "instructions": "Use web_search to find tutorials, then summarize the results.",
        })
        mock_send.return_value = (mock_response, {"total_tokens": 100})
        mock_create.return_value = True

        result = reflect_on_task(
            user_message="Find me a Python asyncio tutorial",
            tool_history=self._make_tool_history(),
            iterations=2,
            outcome="Found and summarized an asyncio tutorial.",
            model="test-model",
        )

        self.assertIsNotNone(result)
        self.assertTrue(result["should_learn"])
        self.assertEqual(result["skill_name"], "python_async_search")

    @patch('utils.openrouter.send_message')
    def test_reflection_parses_should_learn_false(self, mock_send):
        """Test that reflect_on_task correctly parses a 'should_learn: false' response."""
        from utils.reflector import reflect_on_task

        mock_response = json.dumps({
            "should_learn": False,
            "reason": "This was a simple query that doesn't warrant a new skill",
        })
        mock_send.return_value = (mock_response, {"total_tokens": 80})

        # Use a valid tool_history (>= 2 tools) so the reflection actually runs
        result = reflect_on_task(
            user_message="What is 2+2?",
            tool_history=self._make_tool_history(),
            iterations=2,
            outcome="The answer is 4.",
            model="test-model",
        )

        self.assertIsNotNone(result)
        self.assertFalse(result["should_learn"])

    @patch('utils.openrouter.send_message')
    def test_reflection_handles_malformed_json(self, mock_send):
        """Test that reflect_on_task handles malformed LLM responses gracefully."""
        from utils.reflector import reflect_on_task

        mock_send.return_value = ("This is not JSON at all.", {"total_tokens": 50})

        result = reflect_on_task(
            user_message="Some query",
            tool_history=self._make_tool_history(),
            iterations=2,
            outcome="Some outcome",
            model="test-model",
        )

        # Should return None for malformed JSON, not crash
        self.assertIsNone(result)

    @patch('utils.openrouter.send_message')
    def test_reflection_handles_api_error(self, mock_send):
        """Test that reflect_on_task handles API errors gracefully."""
        from utils.reflector import reflect_on_task

        mock_send.side_effect = Exception("API error")

        result = reflect_on_task(
            user_message="Some query",
            tool_history=self._make_tool_history(),
            iterations=2,
            outcome="Some outcome",
            model="test-model",
        )

        self.assertTrue(result is None or isinstance(result, dict))

    def test_reflection_skips_with_insufficient_tools(self):
        """Test that reflect_on_task skips reflection when fewer than 2 tools were used."""
        from utils.reflector import reflect_on_task

        result = reflect_on_task(
            user_message="Hello",
            tool_history=[],
            iterations=0,
            outcome="Hi there!",
            model="test-model",
        )

        # Should return None (skipped, not enough tools)
        self.assertIsNone(result)

    @patch('utils.skills.create_learned_skill')
    @patch('utils.openrouter.send_message')
    def test_reflection_extracts_all_fields(self, mock_send, mock_create):
        """Test that all expected fields are extracted from a valid reflection."""
        from utils.reflector import reflect_on_task

        mock_response = json.dumps({
            "should_learn": True,
            "skill_name": "weather_and_translate",
            "description": "Get weather and translate the forecast",
            "triggers": ["weather translate", "translate weather"],
            "instructions": "Call weather skill, then translate the result.",
            "arguments": [
                {"name": "location", "type": "string", "required": True, "description": "City name"},
                {"name": "language", "type": "string", "required": True, "description": "Target language"}
            ],
        })
        mock_send.return_value = (mock_response, {"total_tokens": 120})
        mock_create.return_value = True

        result = reflect_on_task(
            user_message="Get the weather in Tokyo and translate to French",
            tool_history=[
                {"tool": "weather", "args": {"location": "Tokyo"}, "result": "Sunny, 25C", "iteration": 1},
                {"tool": "translate", "args": {"text": "Sunny, 25C", "to": "fr"}, "result": "Ensoleillé, 25C", "iteration": 2},
            ],
            iterations=2,
            outcome="Tokyo weather translated to French",
            model="test-model",
        )

        self.assertIsNotNone(result)
        self.assertTrue(result["should_learn"])
        self.assertEqual(result["skill_name"], "weather_and_translate")
        self.assertEqual(len(result["triggers"]), 2)


class TestConsolidateMemory(unittest.TestCase):
    """Test consolidate_memory() — appends to MEMORY.md."""

    @patch('utils.context.append_to_memory_md')
    def test_consolidate_calls_append(self, mock_append):
        """Test that consolidate_memory calls append_to_memory_md (via context module)."""
        from utils.reflector import consolidate_memory

        mock_append.return_value = True

        result = consolidate_memory(
            user_message="Search for Python tips and tricks for beginners",
            response="Here are some Python tips and tricks for beginners to improve their coding skills...",
            tool_history=[{"tool": "web_search", "args": {"query": "Python tips"}, "result": "results...", "iteration": 1}],
        )

        mock_append.assert_called_once()
        self.assertTrue(result)

    @patch('utils.context.append_to_memory_md')
    def test_consolidate_handles_failure(self, mock_append):
        """Test that consolidate_memory handles Firestore failures gracefully."""
        from utils.reflector import consolidate_memory

        mock_append.return_value = False

        result = consolidate_memory(
            user_message="This is a long enough test query for consolidation",
            response="This is a long enough test response for the consolidation to proceed properly.",
            tool_history=[],
        )

        self.assertFalse(result)

    def test_consolidate_skips_short_messages(self):
        """Test that consolidate_memory skips very short messages."""
        from utils.reflector import consolidate_memory

        # Too short — should return False without calling append
        result = consolidate_memory(
            user_message="Hi",
            response="Hello!",
            tool_history=[],
        )

        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
