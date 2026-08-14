"""Writer tests. Phase 1.

Skipped until writer/claude-state-writer.py exists. The cases below are the
required coverage, named now so the gap is visible in the test report rather
than forgotten.
"""

import unittest

import support

WRITER_MISSING = not support.WRITER.exists()
reason = f"Phase 1: {support.WRITER.name} not written yet"


@unittest.skipIf(WRITER_MISSING, reason)
class TestTransitionTable(unittest.TestCase):
    """Feed each fixture on stdin, assert the resulting state file."""

    def test_every_row_of_the_transition_table(self):
        raise NotImplementedError

    def test_session_end_deletes_the_record_and_frees_its_slot(self):
        raise NotImplementedError

    def test_stop_failure_records_error_kind_from_the_matcher(self):
        raise NotImplementedError

    def test_user_prompt_submit_clears_a_stale_flag(self):
        raise NotImplementedError


@unittest.skipIf(WRITER_MISSING, reason)
class TestInvariants(unittest.TestCase):
    def test_no_prompt_or_tool_input_reaches_the_state_file(self):
        """Spec 4.2. Assert every sentinel in support.SENTINELS is absent from
        the state file after feeding every fixture through the writer."""
        raise NotImplementedError

    def test_tool_name_is_recorded_but_nothing_else_from_tool_input(self):
        raise NotImplementedError

    def test_exits_zero_on_malformed_stdin(self):
        raise NotImplementedError

    def test_exits_zero_when_the_state_directory_is_unwritable(self):
        raise NotImplementedError

    def test_traceback_goes_to_the_err_file_not_stdout(self):
        raise NotImplementedError

    def test_all_times_are_float_epoch_seconds(self):
        raise NotImplementedError

    def test_starttime_is_stored_alongside_every_pid(self):
        raise NotImplementedError

    def test_state_file_mode_is_0600_and_directory_0700(self):
        raise NotImplementedError

    def test_imports_are_standard_library_only(self):
        raise NotImplementedError


@unittest.skipIf(WRITER_MISSING, reason)
class TestConcurrency(unittest.TestCase):
    def test_twenty_parallel_writers_lose_no_updates(self):
        """Claude Code runs matching hooks in parallel; concurrent writes are
        the normal case. Assert no corruption and no lost updates."""
        raise NotImplementedError


@unittest.skipIf(WRITER_MISSING, reason)
class TestSlots(unittest.TestCase):
    def test_lowest_numbered_free_slot_is_taken(self):
        raise NotImplementedError

    def test_a_session_keeps_its_slot_for_its_entire_life(self):
        raise NotImplementedError

    def test_overflow_when_no_slot_is_free_and_nothing_is_evictable(self):
        raise NotImplementedError


if __name__ == "__main__":
    unittest.main()
