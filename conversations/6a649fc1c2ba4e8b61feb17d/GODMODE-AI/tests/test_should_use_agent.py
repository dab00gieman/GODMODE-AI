"""
Tests for should_use_agent() routing decisions (Task 6 — tightened triggers).

This test suite uses a table of sample messages → expected True/False,
updated as the trigger list is tuned with real production data.

Tests:
- Tool-shaped phrasing triggers agent mode (True)
- Plain conversation does NOT trigger agent mode (False)
- URLs trigger agent mode (True)
- Code blocks trigger agent mode (True)
- Math expressions trigger agent mode (True)
- Previously loose keywords now correctly return False
"""

import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


class TestShouldUseAgent(unittest.TestCase):
    """Test should_use_agent() routing decisions."""

    # ──── Messages that SHOULD trigger agent mode ────
    SHOULD_TRIGGER = [
        "search for Python tutorials",
        "what is the weather in Lagos?",
        "calculate 15 * 23 + 7",
        "translate this to French: hello world",
        "fetch this url: https://example.com",
        "look up the capital of France",
        "summarize this article: ...",
        "http://example.com check this out",
        "https://news.example.com/article",
        "run this code:\n```python\nprint('hello')\n```",
        "```python\nfor i in range(10):\n    print(i)\n```",
        "execute this: print('hello')",
        "what time is it in Tokyo?",
        "convert 100 celsius to fahrenheit",
        "search the web for latest AI news",
        "current price of AAPL stock",
    ]

    # ──── Messages that should NOT trigger agent mode ────
    # Task 6: These were previously triggering agent mode due to loose keywords
    SHOULD_NOT_TRIGGER = [
        "What's the deal with quantum physics?",
        "Help me plan my week",
        "Compare these two ideas I have",
        "Analyze this poem for me",
        "The current situation is complex",
        "What's the best way to learn Python?",
        "I love coding on weekends",
        "Let's plan a trip to Japan",
        "Can you analyze the themes in this book?",
        "What's the meaning of life?",
        "Code is just logic, you know?",
        "Tell me about the history of Rome",
        "How do I improve my writing?",
        "What are your thoughts on AI ethics?",
    ]

    def test_should_trigger_agent_mode(self):
        from utils.agent import should_use_agent
        for msg in self.SHOULD_TRIGGER:
            with self.subTest(msg=msg[:50]):
                result = should_use_agent(msg)
                self.assertTrue(
                    result,
                    f"Expected should_use_agent=True for: '{msg}'"
                )

    def test_should_not_trigger_agent_mode(self):
        from utils.agent import should_use_agent
        for msg in self.SHOULD_NOT_TRIGGER:
            with self.subTest(msg=msg[:50]):
                result = should_use_agent(msg)
                self.assertFalse(
                    result,
                    f"Expected should_use_agent=False for: '{msg}' (got True — false positive)"
                )

    def test_empty_message_returns_false(self):
        from utils.agent import should_use_agent
        self.assertFalse(should_use_agent(""))

    def test_whitespace_only_returns_false(self):
        from utils.agent import should_use_agent
        self.assertFalse(should_use_agent("   "))

    def test_simple_math_expression(self):
        from utils.agent import should_use_agent
        self.assertTrue(should_use_agent("2 + 2"))
        self.assertTrue(should_use_agent("100 * 50"))

    def test_plain_question_without_tools(self):
        from utils.agent import should_use_agent
        self.assertFalse(should_use_agent("What is love?"))
        self.assertFalse(should_use_agent("Tell me a joke"))

    def test_code_block_detection(self):
        from utils.agent import should_use_agent
        self.assertTrue(should_use_agent("Here's some code:\n```\nx = 1\n```"))
        # Just the word "code" without a code block should NOT trigger
        self.assertFalse(should_use_agent("the code is ready"))


if __name__ == "__main__":
    unittest.main()
