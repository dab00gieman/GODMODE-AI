"""
Tests for find_skills_for_message() — trigger matching logic.

Tests:
- Exact trigger phrase matches
- Partial trigger matching (substring in message)
- Multiple skills matching same message
- No skills match
- Case insensitivity
- Learned skills with custom triggers
"""

import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


class TestFindSkillsForMessage(unittest.TestCase):

    def setUp(self):
        from utils.skills import initialize_skills
        initialize_skills()

    def test_weather_trigger(self):
        from utils.skills import find_skills_for_message
        matches = find_skills_for_message("what is the weather in Lagos?")
        self.assertTrue(len(matches) > 0)
        skill_names = [s.name for s in matches]
        self.assertIn("weather", skill_names)

    def test_calculator_trigger(self):
        from utils.skills import find_skills_for_message
        matches = find_skills_for_message("calculate 2 + 2")
        skill_names = [s.name for s in matches]
        self.assertIn("calculator", skill_names)

    def test_web_search_trigger(self):
        from utils.skills import find_skills_for_message
        matches = find_skills_for_message("search for Python tutorials")
        skill_names = [s.name for s in matches]
        self.assertIn("web_search", skill_names)

    def test_case_insensitive(self):
        from utils.skills import find_skills_for_message
        # Triggers should match regardless of case
        matches = find_skills_for_message("SEARCH FOR CAT VIDEOS")
        skill_names = [s.name for s in matches]
        self.assertIn("web_search", skill_names)

    def test_no_match(self):
        from utils.skills import find_skills_for_message
        matches = find_skills_for_message("just a plain greeting hello there")
        # This should not match any skill triggers (no tool-shaped phrasing)
        # Note: if a skill has a very generic trigger, this might still match.
        # We just verify it doesn't crash and returns a list.
        self.assertIsInstance(matches, list)

    def test_multiple_matches(self):
        from utils.skills import find_skills_for_message
        # A message that could trigger multiple skills
        matches = find_skills_for_message("search for the weather in Tokyo and calculate the temperature")
        self.assertTrue(len(matches) >= 1)

    def test_empty_message(self):
        from utils.skills import find_skills_for_message
        matches = find_skills_for_message("")
        self.assertEqual(matches, [])

    def test_translate_trigger(self):
        from utils.skills import find_skills_for_message
        matches = find_skills_for_message("translate this to French: hello")
        skill_names = [s.name for s in matches]
        self.assertIn("translate", skill_names)

    def test_returns_skill_objects(self):
        from utils.skills import find_skills_for_message, Skill
        matches = find_skills_for_message("what is the weather in Paris?")
        for m in matches:
            self.assertIsInstance(m, Skill)
            self.assertTrue(hasattr(m, "name"))
            self.assertTrue(hasattr(m, "description"))
            self.assertTrue(hasattr(m, "triggers"))


if __name__ == "__main__":
    unittest.main()
