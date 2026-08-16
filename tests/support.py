"""Shared helpers for the test suite. Standard library only."""

import importlib.util
import json
import pathlib
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures"

# `claude agents --json` captures, kept in a subdirectory so the hook-fixture
# tests -- which assert every payload carries hook fields -- do not try to
# validate them. all_fixtures() globs the top level only.
AGENT_FIXTURE_DIR = FIXTURE_DIR / "agents"
GOLDEN_DIR = REPO_ROOT / "tests" / "golden"

EVALUATOR = REPO_ROOT / "evaluator" / "claude-state-eval.py"
CLI = REPO_ROOT / "bin" / "claude-state-panel"

# Strings planted in the fixtures purely so tests can assert they never reach
# the rendered model. See spec 4.2: never persist prompt or tool input.
SENTINELS = (
    "SENTINEL-PROMPT-TEXT",
    "SENTINEL-TOOL-INPUT",
    "SENTINEL-TOOL-OUTPUT",
)

# Spec 4.4. Retained for the hook fixtures, which document the fallback path:
# if `claude agents --json` is withdrawn (it is a research preview -- finding N)
# the writer described in findings I and 2 & 4 is what gets built instead.
# Nothing in the shipping evaluator reads this.
TRANSITION_TABLE = {
    "SessionStart": "starting",
    "UserPromptSubmit": "thinking",
    "PreToolUse": "tool",
    "PostToolUse": "thinking",
    "PostToolBatch": "thinking",
    "PermissionRequest": "waiting-permission",
    "Elicitation": "waiting-elicitation",
    "Stop": "waiting-input",
    "StopFailure": "error",
    "SessionEnd": None,
}

# Deliberately no PRIORITY constant here. Priority is the evaluator's, and a
# copy in the tests would be a second place where truth is computed -- the one
# thing this architecture exists to avoid. Tests import it from the evaluator.


def load_evaluator():
    """Import the evaluator by path; its filename is not a valid module name."""
    spec = importlib.util.spec_from_file_location("claude_state_eval", EVALUATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load(name):
    """Load one hook fixture payload by filename stem."""
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text())


def all_fixtures():
    """Yield (stem, payload) for every hook fixture, in sorted order."""
    for path in sorted(FIXTURE_DIR.glob("*.json")):
        yield path.stem, json.loads(path.read_text())


def agents(name):
    """Load one `claude agents --json` capture by filename stem."""
    return json.loads((AGENT_FIXTURE_DIR / f"{name}.json").read_text())


def session(**overrides):
    """A minimal well-formed CLI session entry, for focused unit tests."""
    entry = {
        "pid": 1234,
        "cwd": "/home/justin/Code/Projects/Example",
        "kind": "interactive",
        "startedAt": 1786830000000,
        "sessionId": "00000000-0000-4000-8000-000000000000",
        "name": "example-00",
        "status": "busy",
    }
    entry.update(overrides)
    return entry


def run_cli(*args, env=None):
    """Run bin/claude-state-panel and return the CompletedProcess."""
    return subprocess.run([sys.executable, str(CLI), *args],
                          capture_output=True, text=True, env=env)
