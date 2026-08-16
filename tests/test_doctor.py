"""Renderer tests: `doctor` and `eval`.

These exercise bin/claude-state-panel end to end as a subprocess, against a
captured `claude agents --json` rather than a live one, so they need no running
Claude Code session and no Plasma shell.

The point of `doctor` is that it renders the *same model* the panel draws. If
these pass and the panel disagrees, the panel is not using the model.
"""

import json
import os
import time
import unittest

import support

evaluator = support.load_evaluator()

NOW = "1786836400.0"
GOLDEN = support.GOLDEN_DIR / "doctor_mixed.txt"
MIXED = str(support.AGENT_FIXTURE_DIR / "mixed.json")


def fixed_env():
    """A reproducible environment: fixed zone, no colour, no locale surprises."""
    env = dict(os.environ)
    env.update(TZ="UTC", NO_COLOR="1", LC_ALL="C")
    return env


class TestEvalSubcommand(unittest.TestCase):
    def test_eval_emits_parseable_json(self):
        proc = support.run_cli("eval", "--json-input", MIXED, "--now", NOW,
                               env=fixed_env())
        self.assertEqual(0, proc.returncode, proc.stderr)
        json.loads(proc.stdout)

    def test_eval_output_matches_the_evaluator_exactly(self):
        """The CLI must not massage the model on its way out."""
        proc = support.run_cli("eval", "--json-input", MIXED, "--now", NOW,
                               env=fixed_env())
        from_cli = json.loads(proc.stdout)

        # Match the subprocess's zone so the localised strings agree, and put
        # this process's zone back afterwards -- a test that leaks TZ makes
        # every later test's failure someone else's problem to diagnose.
        previous = os.environ.get("TZ")
        os.environ["TZ"] = "UTC"
        time.tzset()
        try:
            direct = evaluator.evaluate(support.agents("mixed"), now=float(NOW))
        finally:
            if previous is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = previous
            time.tzset()

        self.assertEqual(direct["sessions"], from_cli["sessions"])
        self.assertEqual(direct["overflow"], from_cli["overflow"])

    def test_slots_option_is_honoured(self):
        proc = support.run_cli("eval", "--json-input", MIXED, "--now", NOW,
                               "--slots", "2", env=fixed_env())
        model = json.loads(proc.stdout)
        self.assertEqual(2, len(model["sessions"]))
        self.assertEqual(4, model["overflow"]["count"])


class TestDoctorSubcommand(unittest.TestCase):
    def _run(self, *extra):
        return support.run_cli("doctor", "--json-input", MIXED, "--now", NOW,
                               *extra, env=fixed_env())

    def test_doctor_runs_clean(self):
        proc = self._run()
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertEqual("", proc.stderr)

    def test_doctor_names_every_visible_session(self):
        proc = self._run()
        for label in ("Glyph-Hunter", "Sentry-MCP", "Claude-State-Panel"):
            self.assertIn(label, proc.stdout)

    def test_doctor_reports_how_many_are_waiting_on_you(self):
        proc = self._run()
        self.assertIn("2 waiting on you", proc.stdout)

    def test_doctor_shows_the_overflow_badge(self):
        proc = self._run("--slots", "2")
        self.assertIn("overflow", proc.stdout)
        self.assertIn("+4", proc.stdout)

    def test_doctor_emits_no_ansi_when_not_a_tty(self):
        """Piping doctor into a bug report must not smuggle escape codes."""
        proc = self._run()
        self.assertNotIn("\033[", proc.stdout)

    def test_doctor_leaks_no_sentinel(self):
        proc = support.run_cli(
            "doctor", "--json-input",
            str(support.AGENT_FIXTURE_DIR / "sensitive.json"),
            "--now", NOW, env=fixed_env())
        for sentinel in support.SENTINELS:
            self.assertNotIn(sentinel, proc.stdout)

    def test_empty_session_list_renders_rather_than_crashing(self):
        empty = support.GOLDEN_DIR.parent / "fixtures" / "agents" / "empty.json"
        empty.write_text("[]\n")
        try:
            proc = support.run_cli("doctor", "--json-input", str(empty),
                                   "--now", NOW, env=fixed_env())
            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertIn("no interactive sessions", proc.stdout)
        finally:
            empty.unlink()


class TestGoldenFile(unittest.TestCase):
    """Locks the rendered output. Regenerate deliberately, never casually:

        TZ=UTC NO_COLOR=1 bin/claude-state-panel doctor \\
            --json-input tests/fixtures/agents/mixed.json \\
            --now 1786836400.0 > tests/golden/doctor_mixed.txt
    """

    def test_doctor_output_matches_the_committed_golden(self):
        proc = support.run_cli("doctor", "--json-input", MIXED, "--now", NOW,
                               env=fixed_env())
        self.assertEqual(GOLDEN.read_text(), proc.stdout,
                         "doctor output changed; see this test's docstring")


class TestExitCodes(unittest.TestCase):
    def test_a_readable_empty_list_is_success_not_failure(self):
        """No sessions is a legitimate answer, not an error."""
        empty = support.AGENT_FIXTURE_DIR / "empty_exit.json"
        empty.write_text("[]\n")
        try:
            proc = support.run_cli("eval", "--json-input", str(empty),
                                   "--now", NOW, env=fixed_env())
            self.assertEqual(0, proc.returncode)
        finally:
            empty.unlink()

    def test_an_unreadable_source_exits_non_zero(self):
        """So a wrapper can tell 'nothing running' from 'could not look'."""
        env = fixed_env()
        env["PATH"] = "/nonexistent"
        proc = support.run_cli("eval", "--now", NOW, env=env)
        self.assertEqual(1, proc.returncode)
        self.assertTrue(json.loads(proc.stdout)["warnings"])


if __name__ == "__main__":
    unittest.main()
