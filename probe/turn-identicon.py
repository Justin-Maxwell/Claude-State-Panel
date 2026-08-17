#!/usr/bin/env python3
"""Emit the project identicon into the chat transcript at the end of a turn.

Companion to `identicon/claude-state-identicon.py emit`, which renders to a
terminal -- ANSI, sixel, kitty. This one renders to a *chat* client, where the
only channel is a `systemMessage` string that gets rendered as markdown, so the
icon travels as a `data:` URI. Verified 2026-08-17: a markdown `data:image/png`
renders inline in the Claude Desktop chat, and at 30x30 it stays in the text
flow rather than being wrapped in a card.

Registered as a `Stop` hook. `Stop` fires on *every* response turn rather than
only on genuine completions -- the exact property that made it useless as a
"Claude is waiting for you" signal (exploration doc, section 1.1) is the
property this needs. The defect is the feature.

`systemMessage` is delivered to the *user's* transcript rather than to Claude,
so the output is deterministic: it does not depend on the model choosing to
comply, cannot be dropped under context pressure, and costs no tokens.

Nothing here derives an identicon. The key and the pixels both come from
`identicon/claude-state-identicon.py`, which implements
`docs/project-identicon-spec.md`. This file only wraps them for a chat client.

**This script is the generator, not the runtime.** An identicon is a constant
for a repository, so running a Python process every turn to rederive it is work
for its own sake -- 68ms measured, against 2.3ms for a shell `printf` of the
finished string. `--settings` bakes that string into the project's own
`.claude/settings.json`, which is what is actually registered. Running this
file as a hook still works and is what the tests exercise, but it is the
fallback, not the design.

    probe/turn-identicon.py --settings > .claude/settings.json

Status: probe. `.claude/settings.json` in *this* repository is live; nothing is
registered in `~/.claude/settings.json`.
"""

import base64
import importlib.util
import json
import os
import shlex
import sys

SIZE = 30

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_IMPLEMENTATION = os.path.join(_ROOT, "identicon", "claude-state-identicon.py")


def _identicon():
    spec = importlib.util.spec_from_file_location("claude_state_identicon",
                                                  _IMPLEMENTATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def message_for(cwd):
    """The exact `systemMessage` string for a project directory."""
    module = _identicon()
    key, _source = module.resolve_key(cwd)
    png = module.render_png(key, SIZE)
    # Empty alt text: the icon is the whole message. A printed name beside it is
    # redundant when you already know which window you are looking at, and it is
    # the identicon that has to do the work.
    return f"![](data:image/png;base64,{base64.b64encode(png).decode('ascii')})"


PAYLOAD_NAME = "identicon.json"
HOOK_COMMAND = "cat ${CLAUDE_PROJECT_DIR}/.claude/" + PAYLOAD_NAME


def payload_for(cwd):
    """The hook's entire stdout: the finished `systemMessage`, ready to print."""
    return json.dumps({"systemMessage": message_for(cwd)}, separators=(",", ":"))


def settings_fragment():
    """A project-level hook that emits the identicon with no derivation at all.

    The identicon is a *constant* for a repository. Deriving it once per turn --
    a Python process, a module import and two git calls, 68ms measured -- to
    reproduce a string that cannot change is work for its own sake. Reading the
    finished string costs 2.4ms, and nothing can go wrong in between.

    The payload is a *separate file*, not a literal in here. `settings.json` is
    hand-edited configuration; a 219-character base64 blob inside it makes every
    diff unreadable and invites someone to break the icon while editing an
    unrelated hook. Split, the config never changes when the icon does.

    `${CLAUDE_PROJECT_DIR}` rather than a relative path: hook commands resolve
    relative paths against the working directory, and the working directory can
    change mid-session. The placeholder is documented as surviving that.

    This belongs in the *project's* `.claude/`, not the user's -- there is no
    global place a per-repository constant could live, and a user-level hook
    would have to rederive the key every turn just to learn which repository it
    was in, which is the entire cost being removed.

    It survives cloning, because the key is the git remote rather than a path
    (finding Q). The committed files are correct in every checkout of this
    repository, on any machine, which a path-keyed identicon could never manage.
    """
    return {
        "hooks": {
            "Stop": [{"hooks": [{"type": "command", "command": HOOK_COMMAND}]}]
        }
    }


def install(cwd):
    """Write both files under `<cwd>/.claude/`. Returns the paths written."""
    target = os.path.join(cwd, ".claude")
    os.makedirs(target, exist_ok=True)

    settings_path = os.path.join(target, "settings.json")
    payload_path = os.path.join(target, PAYLOAD_NAME)

    with open(settings_path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(settings_fragment(), indent=2) + "\n")
    with open(payload_path, "w", encoding="utf-8") as handle:
        handle.write(payload_for(cwd) + "\n")

    return settings_path, payload_path


def main():
    if "--settings" in sys.argv:
        print(json.dumps(settings_fragment(), indent=2))
        return 0
    if "--payload" in sys.argv:
        print(payload_for(os.getcwd()))
        return 0
    if "--install" in sys.argv:
        for path in install(os.getcwd()):
            print(path)
        return 0

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    cwd = payload.get("cwd") or ""
    if not cwd:
        return 0

    try:
        message = message_for(cwd)
    except Exception:
        # A hook that fails must not disturb the session it is decorating.
        return 0

    print(json.dumps({"systemMessage": message}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

# To register this in another repository:
#
#   cd /path/to/that/repo
#   /path/to/probe/turn-identicon.py --settings > .claude/settings.json
#
# Project-level, deliberately. There is no global place a per-repository
# constant could live, and a user-level hook would have to rederive the key on
# every turn to know which repository it was in -- which is the cost this
# exists to remove.
#
# The generated literal survives cloning: the key is the git remote, not a
# path, so the committed settings are correct in every checkout on every
# machine. Regenerate only if the identicon spec changes; the test suite fails
# if the committed literal and the derivation ever disagree.
