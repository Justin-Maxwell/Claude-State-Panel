"""Evaluator tests. Phase 1.

The evaluator is a pure function from a `claude agents --json` array to the
model every renderer draws, so all of this runs with no live Claude Code
session, no Plasma shell, and no network.
"""

import json
import os
import time
import unittest

import support

evaluator = support.load_evaluator()

NOW = 1786836400.0  # fixed clock, so ages are exact rather than approximately


class TestClassify(unittest.TestCase):
    """Mapping the CLI's vocabulary onto ours. Finding N."""

    def test_busy_is_working(self):
        state, warning = evaluator.classify(support.session(status="busy"))
        self.assertEqual("working", state)
        self.assertIsNone(warning)

    def test_idle_is_idle(self):
        state, warning = evaluator.classify(support.session(status="idle"))
        self.assertEqual("idle", state)
        self.assertIsNone(warning)

    def test_permission_prompt_is_waiting_permission(self):
        state, warning = evaluator.classify(support.session(
            status="waiting", waitingFor="permission prompt"))
        self.assertEqual("waiting-permission", state)
        self.assertIsNone(warning)

    def test_input_needed_is_waiting_answer(self):
        state, warning = evaluator.classify(support.session(
            status="waiting", waitingFor="input needed"))
        self.assertEqual("waiting-answer", state)
        self.assertIsNone(warning)

    def test_sandbox_request_renders_as_a_permission_decision(self):
        state, _ = evaluator.classify(support.session(
            status="waiting", waitingFor="sandbox request"))
        self.assertEqual("waiting-permission", state)

    def test_unknown_waiting_reason_still_counts_as_blocked(self):
        """A future release adding a reason must not silently drop a session
        that is genuinely blocked on Justin."""
        state, warning = evaluator.classify(support.session(
            status="waiting", waitingFor="something new"))
        self.assertIn(state, evaluator.ATTENTION)
        self.assertIsNotNone(warning)

    def test_unknown_status_is_unknown_and_warns(self):
        state, warning = evaluator.classify(support.session(status="frobnicating"))
        self.assertEqual("unknown", state)
        self.assertIsNotNone(warning)

    def test_every_state_has_a_glyph_a_colour_and_a_priority(self):
        for state in evaluator.PRIORITY:
            with self.subTest(state=state):
                self.assertIn(state, evaluator.GLYPH)
                self.assertIn(state, evaluator.COLOUR)

    def test_attention_states_are_a_subset_of_priority(self):
        self.assertTrue(set(evaluator.ATTENTION).issubset(set(evaluator.PRIORITY)))


class TestNonInteractiveSessions(unittest.TestCase):
    """Justin's ruling, 2026-08-14: non-interactive sessions never claim a slot.

    Under the hook architecture this needed a discriminator nobody could derive
    (open question 10). The CLI reports `kind`, so it is one comparison.
    """

    def test_background_sessions_are_excluded(self):
        model = evaluator.evaluate(support.agents("mixed"), now=NOW)
        kinds = {s["session_id"] for s in model["sessions"]}
        self.assertNotIn("7d0ccdb5-0000-4000-8000-000000000003", kinds)

    def test_a_background_only_list_yields_no_sessions(self):
        model = evaluator.evaluate([support.session(kind="background")], now=NOW)
        self.assertEqual([], model["sessions"])
        self.assertEqual(0, model["session_count"])

    def test_an_unknown_kind_is_excluded_rather_than_guessed(self):
        model = evaluator.evaluate([support.session(kind="something-else")], now=NOW)
        self.assertEqual([], model["sessions"])


class TestOrderingAndPriority(unittest.TestCase):
    def test_blocked_sessions_sort_above_everything(self):
        model = evaluator.evaluate(support.agents("mixed"), now=NOW)
        states = [s["state"] for s in model["sessions"]]
        self.assertEqual("waiting-permission", states[0])
        self.assertEqual("waiting-answer", states[1])

    def test_idle_outranks_working_because_idle_is_your_turn(self):
        self.assertLess(evaluator.PRIORITY.index("idle"),
                        evaluator.PRIORITY.index("working"))

    def test_order_is_stable_across_identical_polls(self):
        """A panel that reshuffles under the cursor is worse than a wrong one."""
        raw = support.agents("mixed")
        first = evaluator.evaluate(raw, now=NOW)
        second = evaluator.evaluate(list(reversed(raw)), now=NOW)
        self.assertEqual([s["session_id"] for s in first["sessions"]],
                         [s["session_id"] for s in second["sessions"]])

    def test_within_a_state_the_oldest_session_sorts_first(self):
        raw = [
            support.session(sessionId="young", startedAt=1786836000000, status="idle"),
            support.session(sessionId="old", startedAt=1786830000000, status="idle"),
        ]
        model = evaluator.evaluate(raw, now=NOW)
        self.assertEqual(["old", "young"],
                         [s["session_id"] for s in model["sessions"]])


class TestSlotsAndOverflow(unittest.TestCase):
    def test_slots_are_numbered_from_zero_without_gaps(self):
        model = evaluator.evaluate(support.agents("mixed"), now=NOW, slots=4)
        self.assertEqual([0, 1, 2, 3], [s["slot"] for s in model["sessions"]])

    def test_sessions_beyond_the_slot_count_overflow(self):
        model = evaluator.evaluate(support.agents("mixed"), now=NOW, slots=4)
        self.assertEqual(4, len(model["sessions"]))
        self.assertEqual(2, model["overflow"]["count"])

    def test_overflowed_sessions_carry_no_slot(self):
        model = evaluator.evaluate(support.agents("mixed"), now=NOW, slots=4)
        for entry in model["overflow"]["sessions"]:
            self.assertIsNone(entry["slot"])

    def test_the_badge_borrows_the_highest_priority_hidden_session(self):
        """Design decision, 2026-08-14: the overflow badge carries the
        highest-priority overflow session's glyph and colour."""
        model = evaluator.evaluate(support.agents("mixed"), now=NOW, slots=1)
        hidden = model["overflow"]["sessions"][0]
        self.assertEqual(hidden["state"], model["overflow"]["state"])
        self.assertEqual(hidden["glyph"], model["overflow"]["glyph"])
        self.assertEqual(hidden["colour"], model["overflow"]["colour"])

    def test_a_hidden_blocked_session_still_reports_attention(self):
        model = evaluator.evaluate(support.agents("mixed"), now=NOW, slots=1)
        self.assertTrue(model["overflow"]["attention"])

    def test_no_overflow_reports_a_null_badge(self):
        model = evaluator.evaluate(support.agents("mixed"), now=NOW, slots=99)
        self.assertEqual(0, model["overflow"]["count"])
        self.assertIsNone(model["overflow"]["state"])
        self.assertIsNone(model["overflow"]["glyph"])


class TestLabels(unittest.TestCase):
    def test_label_is_the_basename_of_cwd(self):
        model = evaluator.evaluate(
            [support.session(cwd="/home/justin/Code/Projects/Sentry-MCP")], now=NOW)
        self.assertEqual("Sentry-MCP", model["sessions"][0]["label"])

    def test_a_trailing_slash_does_not_produce_an_empty_label(self):
        model = evaluator.evaluate(
            [support.session(cwd="/home/justin/Code/Projects/Sentry-MCP/")], now=NOW)
        self.assertEqual("Sentry-MCP", model["sessions"][0]["label"])

    def test_colliding_labels_gain_a_discriminator(self):
        """Design decision, 2026-08-14: only collisions get a discriminator."""
        model = evaluator.evaluate(support.agents("mixed"), now=NOW, slots=99)
        labels = [s["label"] for s in model["sessions"]]
        clautana = [label for label in labels if label.startswith("Clautana")]
        self.assertEqual(2, len(clautana))
        self.assertEqual(2, len(set(clautana)), f"still colliding: {clautana}")

    def test_non_colliding_labels_stay_clean(self):
        model = evaluator.evaluate(support.agents("mixed"), now=NOW, slots=99)
        labels = [s["label"] for s in model["sessions"]]
        self.assertIn("Sentry-MCP", labels)


class TestPrivacy(unittest.TestCase):
    """Spec 4.2. The CLI hands us fields we must not pass on."""

    def test_no_sentinel_reaches_the_model(self):
        model = evaluator.evaluate(support.agents("sensitive"), now=NOW)
        blob = json.dumps(model)
        for sentinel in support.SENTINELS:
            with self.subTest(sentinel=sentinel):
                self.assertNotIn(sentinel, blob)

    def test_no_sentinel_survives_the_mixed_fixture_either(self):
        blob = json.dumps(evaluator.evaluate(support.agents("mixed"), now=NOW))
        for sentinel in support.SENTINELS:
            self.assertNotIn(sentinel, blob)

    def test_only_allowlisted_keys_are_copied_from_a_session(self):
        """Copying the CLI entry wholesale is the obvious mistake; this fails
        if anyone ever does it."""
        allowed = {
            "session_id", "short_id", "pid", "cwd", "label", "name", "state",
            "glyph", "colour", "attention", "waiting_for", "started_at",
            "started_at_local", "age_secs", "slot",
        }
        model = evaluator.evaluate(support.agents("sensitive"), now=NOW)
        self.assertEqual(set(), set(model["sessions"][0]) - allowed)


class TestEdgeCases(unittest.TestCase):
    def test_zero_sessions_produces_valid_output(self):
        model = evaluator.evaluate([], now=NOW)
        self.assertEqual([], model["sessions"])
        self.assertEqual(0, model["attention_count"])
        self.assertEqual(0, model["overflow"]["count"])
        self.assertEqual(evaluator.SCHEMA, model["schema"])

    def test_a_session_missing_startedat_does_not_crash(self):
        entry = support.session()
        del entry["startedAt"]
        model = evaluator.evaluate([entry], now=NOW)
        self.assertIsNone(model["sessions"][0]["age_secs"])

    def test_a_session_missing_cwd_still_renders(self):
        model = evaluator.evaluate([support.session(cwd=None)], now=NOW)
        self.assertTrue(model["sessions"][0]["label"])

    def test_the_model_is_json_serialisable(self):
        json.dumps(evaluator.evaluate(support.agents("mixed"), now=NOW))

    def test_attention_count_counts_overflowed_sessions_too(self):
        """A blocked session hidden behind the badge is still waiting on you."""
        model = evaluator.evaluate(support.agents("mixed"), now=NOW, slots=1)
        self.assertEqual(2, model["attention_count"])


class TestFetchFailures(unittest.TestCase):
    """A panel that shows a stale lie is worse than one that says it cannot look."""

    def test_missing_binary_yields_a_warning_not_an_exception(self):
        sessions, warnings = evaluator.fetch(argv=("definitely-not-a-real-binary",))
        self.assertEqual([], sessions)
        self.assertTrue(warnings)

    def test_non_zero_exit_yields_a_warning(self):
        sessions, warnings = evaluator.fetch(argv=("false",))
        self.assertEqual([], sessions)
        self.assertTrue(warnings)

    def test_unparseable_output_yields_a_warning(self):
        sessions, warnings = evaluator.fetch(argv=("echo", "not json"))
        self.assertEqual([], sessions)
        self.assertTrue(warnings)

    def test_a_json_object_instead_of_an_array_is_rejected(self):
        sessions, warnings = evaluator.fetch(argv=("echo", '{"not": "an array"}'))
        self.assertEqual([], sessions)
        self.assertTrue(warnings)

    def test_warnings_from_fetch_survive_into_the_model(self):
        model = evaluator.evaluate([], now=NOW, warnings=["carried through"])
        self.assertIn("carried through", model["warnings"])


class TestTimezones(unittest.TestCase):
    """Raw epochs identical across timezones; only localised strings differ."""

    def setUp(self):
        self._tz = os.environ.get("TZ")

    def tearDown(self):
        if self._tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = self._tz
        time.tzset()

    def _model_under(self, tz):
        os.environ["TZ"] = tz
        time.tzset()
        return evaluator.evaluate(support.agents("mixed"), now=NOW)

    def test_raw_epochs_are_identical_across_timezones(self):
        zones = ["Pacific/Auckland", "UTC", "America/New_York"]
        raws = []
        for zone in zones:
            model = self._model_under(zone)
            raws.append([s["started_at"] for s in model["sessions"]]
                        + [model["generated_at"]])
        self.assertEqual(raws[0], raws[1])
        self.assertEqual(raws[1], raws[2])

    def test_localised_strings_do_differ(self):
        auckland = self._model_under("Pacific/Auckland")["generated_at_local"]
        new_york = self._model_under("America/New_York")["generated_at_local"]
        self.assertNotEqual(auckland, new_york)

    def test_every_timestamp_is_emitted_raw_as_well_as_localised(self):
        model = self._model_under("UTC")
        for entry in model["sessions"]:
            self.assertIsInstance(entry["started_at"], float)
            self.assertIsInstance(entry["started_at_local"], str)
        self.assertIsInstance(model["generated_at"], float)
        self.assertIsInstance(model["generated_at_local"], str)


if __name__ == "__main__":
    unittest.main()
