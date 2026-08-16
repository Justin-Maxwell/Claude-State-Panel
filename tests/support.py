"""Shared helpers for the test suite. Standard library only."""

import importlib.util
import json
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures"

WRITER = REPO_ROOT / "writer" / "claude-state-writer.py"
EVALUATOR = REPO_ROOT / "evaluator" / "claude-state-eval.py"
IDENTICON = REPO_ROOT / "identicon" / "claude-state-identicon.py"


def load_script(path, name):
    """Import a hyphenated, extensionless-by-convention script as a module.

    The tools are named for the command line, not for `import`, so the suite
    loads them by path rather than renaming them to suit the tests.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

# Strings planted in the fixtures purely so tests can assert they never reach
# the state file. See spec 4.2: never persist prompt or tool input.
SENTINELS = (
    "SENTINEL-PROMPT-TEXT",
    "SENTINEL-TOOL-INPUT",
    "SENTINEL-TOOL-OUTPUT",
)

# Spec 4.4. SessionEnd deletes the record and so has no resulting state.
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

# Spec 5.4, highest priority first.
PRIORITY = [
    "error",
    "waiting-permission",
    "waiting-elicitation",
    "waiting-input",
    "tool",
    "thinking",
    "starting",
]


def load(name):
    """Load one fixture payload by filename stem."""
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text())


def all_fixtures():
    """Yield (stem, payload) for every fixture, in sorted order."""
    for path in sorted(FIXTURE_DIR.glob("*.json")):
        yield path.stem, json.loads(path.read_text())
