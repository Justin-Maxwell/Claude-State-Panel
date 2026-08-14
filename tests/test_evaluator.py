"""Evaluator tests. Phase 1.

Skipped until evaluator/claude-state-eval.py exists. State files are
constructed by hand; no live Claude Code session and no Plasma shell.
"""

import unittest

import support

EVALUATOR_MISSING = not support.EVALUATOR.exists()
reason = f"Phase 1: {support.EVALUATOR.name} not written yet"


@unittest.skipIf(EVALUATOR_MISSING, reason)
class TestLiveness(unittest.TestCase):
    def test_missing_proc_entry_is_reaped(self):
        raise NotImplementedError

    def test_starttime_mismatch_is_reaped_as_pid_reuse(self):
        raise NotImplementedError

    def test_a_live_session_survives_evaluation(self):
        raise NotImplementedError

    def test_the_evaluator_never_mutates_the_state_file(self):
        """Two renderers polling concurrently must never race. Assert mtime and
        bytes are unchanged after evaluation."""
        raise NotImplementedError


@unittest.skipIf(EVALUATOR_MISSING, reason)
class TestStaleness(unittest.TestCase):
    def test_thinking_past_the_ceiling_is_flagged_stale(self):
        raise NotImplementedError

    def test_tool_past_the_ceiling_is_flagged_stale(self):
        raise NotImplementedError

    def test_stale_does_not_change_the_underlying_state(self):
        raise NotImplementedError

    def test_stale_emits_a_warning_every_time(self):
        raise NotImplementedError

    def test_a_waiting_state_is_never_flagged_stale_by_a_ceiling(self):
        raise NotImplementedError


@unittest.skipIf(EVALUATOR_MISSING, reason)
class TestPriorityAndOrdering(unittest.TestCase):
    def test_attention_state_is_the_highest_priority_live_state(self):
        raise NotImplementedError

    def test_priority_order_matches_the_spec(self):
        self.assertEqual(
            ["error", "waiting-permission", "waiting-elicitation",
             "waiting-input", "tool", "thinking", "starting"],
            support.PRIORITY,
        )

    def test_stale_sessions_sort_last_regardless_of_state(self):
        raise NotImplementedError


@unittest.skipIf(EVALUATOR_MISSING, reason)
class TestEdgeCases(unittest.TestCase):
    def test_zero_sessions_produces_valid_output(self):
        raise NotImplementedError

    def test_overflow_beyond_n_slots(self):
        raise NotImplementedError

    def test_slot_eviction_after_idle_evict_secs(self):
        raise NotImplementedError

    def test_missing_state_file_produces_valid_empty_output(self):
        raise NotImplementedError

    def test_corrupt_state_file_produces_a_warning_not_a_crash(self):
        raise NotImplementedError


@unittest.skipIf(EVALUATOR_MISSING, reason)
class TestTimezones(unittest.TestCase):
    def test_raw_epochs_are_identical_across_timezones(self):
        """Run under Pacific/Auckland, UTC, and America/New_York. Raw epochs
        identical; only localised strings differ."""
        raise NotImplementedError

    def test_every_timestamp_is_emitted_raw_as_well_as_localised(self):
        raise NotImplementedError


@unittest.skipIf(EVALUATOR_MISSING, reason)
class TestGoldenFiles(unittest.TestCase):
    def test_doctor_json_matches_committed_golden(self):
        raise NotImplementedError


if __name__ == "__main__":
    unittest.main()
