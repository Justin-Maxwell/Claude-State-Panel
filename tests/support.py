"""Shared helpers for the test suite. Standard library only."""

import importlib.util
import json
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures"

WRITER = REPO_ROOT / "writer" / "claude-state-writer.py"
EVALUATOR = REPO_ROOT / "evaluator" / "claude-state-eval.py"
IDENTICON = REPO_ROOT / "identicon" / "claude-state-identicon.py"
IDENTICON_VECTORS = REPO_ROOT / "identicon" / "vectors.json"
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
    """Load one fixture payload by filename stem."""
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text())


def all_fixtures():
    """Yield (stem, payload) for every fixture, in sorted order."""
    for path in sorted(FIXTURE_DIR.glob("*.json")):
        yield path.stem, json.loads(path.read_text())
