"""Fixture integrity.

These run from Phase 0 onward, before any implementation exists. They assert
the synthetic payloads are well formed and that the transition table is fully
covered, so a fixture gap shows up as a failing test rather than as a silently
untested row.
"""

import unittest

import support


class TestFixturesAreWellFormed(unittest.TestCase):
    def test_at_least_one_fixture_exists(self):
        self.assertTrue(list(support.all_fixtures()))

    def test_every_payload_carries_the_universal_fields(self):
        # Spec 4.1: every payload carries session_id, cwd, hook_event_name.
        for stem, payload in support.all_fixtures():
            with self.subTest(fixture=stem):
                for key in ("session_id", "cwd", "hook_event_name"):
                    self.assertIn(key, payload)
                    self.assertIsInstance(payload[key], str)
                    self.assertTrue(payload[key])

    def test_tool_events_carry_a_tool_name(self):
        for stem, payload in support.all_fixtures():
            if payload["hook_event_name"] in ("PreToolUse", "PostToolUse"):
                with self.subTest(fixture=stem):
                    self.assertIn("tool_name", payload)


class TestTransitionTableCoverage(unittest.TestCase):
    def test_every_transition_row_has_a_fixture(self):
        covered = {p["hook_event_name"] for _, p in support.all_fixtures()}
        missing = set(support.TRANSITION_TABLE) - covered
        self.assertEqual(set(), missing, f"transition rows without a fixture: {sorted(missing)}")

    def test_ask_user_question_is_covered(self):
        # Open question 1, the single most valuable thing Phase 0 can confirm.
        payload = support.load("pre_tool_use_ask_user_question")
        self.assertEqual("PreToolUse", payload["hook_event_name"])
        self.assertEqual("AskUserQuestion", payload["tool_name"])

    def test_a_second_concurrent_session_is_available(self):
        # Slot assignment and priority ordering need more than one session.
        ids = {p["session_id"] for _, p in support.all_fixtures()}
        self.assertGreaterEqual(len(ids), 2)


class TestSentinelsArePresentToBeAssertedAgainst(unittest.TestCase):
    """The privacy tests are only meaningful if the fixtures actually carry
    sensitive-looking content. Guard against someone tidying it away."""

    def test_prompt_payload_carries_a_sentinel(self):
        payload = support.load("user_prompt_submit")
        self.assertIn("SENTINEL-PROMPT-TEXT", payload["prompt"])

    def test_tool_input_payload_carries_a_sentinel(self):
        payload = support.load("pre_tool_use_bash")
        self.assertIn("SENTINEL-TOOL-INPUT", payload["tool_input"]["command"])


if __name__ == "__main__":
    unittest.main()
