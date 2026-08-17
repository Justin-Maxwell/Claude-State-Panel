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
IDENTICON = REPO_ROOT / "identicon" / "claude-state-identicon.py"
IDENTICON_SPEC = REPO_ROOT / "docs" / "project-identicon-spec.md"


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

# --- State vocabulary -------------------------------------------------------
# docs/state-vocabulary.md, which supersedes the spec 5 glyph and colour table.
# Held here so the vocabulary is checked rather than merely written down.

# The nine text colour roles Kirigami actually exposes. Verified against
# src/platform/platformtheme.h at KDE/kirigami@master, finding H.
KIRIGAMI_TEXT_ROLES = {
    "textColor",
    "disabledTextColor",
    "activeTextColor",
    "linkColor",
    "visitedLinkColor",
    "negativeTextColor",
    "neutralTextColor",
    "positiveTextColor",
    "highlightColor",
}

# One role per state. No role appears twice; that is the point.
STATE_ROLES = {
    "error": "negativeTextColor",
    "waiting-permission": "neutralTextColor",
    "waiting-elicitation": "activeTextColor",
    "waiting-input": "positiveTextColor",
    "tool": "linkColor",
    "thinking": "textColor",
    "starting": "disabledTextColor",
}

# Reserved for the overflow badge and any future selection affordance, so a
# later change cannot quietly claim them for a state.
RESERVED_ROLES = {"highlightColor", "visitedLinkColor"}

# Base glyph per state. `error` and `tool` resolve further, by subtype.
STATE_GLYPHS = {
    "error": "⛔",
    "waiting-permission": "❗",
    "waiting-elicitation": "❓",
    "waiting-input": "●",
    "tool": "⚙",
    "thinking": "◐",
    "starting": "◌",
}

# tool_name is the one non-universal field the probe ever saw populated.
TOOL_CLASSES = {
    "command": ("Bash",),
    "edit": ("Edit", "Write", "NotebookEdit"),
    "read": ("Read", "Grep", "Glob"),
    "network": ("WebFetch", "WebSearch"),
    "agent": ("Task",),
    "other": (),
}

TOOL_CLASS_GLYPHS = {
    "command": "▶",
    "edit": "✎",
    "read": "⌕",
    "network": "⇅",
    "agent": "⑂",
    "other": "⚙",
}

# error_kind arrives from matcher-specific registration, finding C.
ERROR_KIND_GLYPHS = {
    "rate_limit": "⏳",
    "overloaded": "☁",
    "billing_error": "💳",
    None: "⛔",
}

# Something waiting on you does not become less true with time.
ATTENTION_STATES = {"error", "waiting-permission", "waiting-elicitation"}

INTENSITY_FLOOR = 0.4

# Ordinals appear only when a project holds more than one live session.
ORDINAL_GLYPHS = "¹²³⁴⁵⁶⁷⁸⁹"
ORDINAL_OVERFLOW = "⁺"

# Glyphs suspected of rendering as colour emoji rather than as themed text. A
# colour-emoji glyph paints its own colour and overrides the theme role, which
# would break the one role per state rule for that state alone.
#
# UNVERIFIED. Establishing this needs the Unicode Emoji_Presentation property,
# which the standard library does not expose and which could not be fetched.
# Open item 15 resolves it on the machine, by rendering. Three of these — ⛔ ❗ ❓
# — are inherited from the spec 5 table, so this predates the vocabulary work.
EMOJI_PRESENTATION_SUSPECT = {"⛔", "❗", "❓", "⏳", "💳", "☁"}


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
