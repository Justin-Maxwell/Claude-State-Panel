#!/usr/bin/env python3
"""Emit the project identicon into the chat transcript at the end of a turn.

Companion to `identicon/claude-state-identicon.py emit`, which renders to a
terminal -- ANSI, sixel, kitty. This one renders to a *chat* client, where the
only channel is a `systemMessage` string that gets rendered as markdown, so the
icon travels as a `data:` URI. Verified 2026-08-17: a markdown `data:image/png`
renders inline in the Claude Desktop chat, and at this size it stays in the
text flow rather than being wrapped in a card.

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

**This file no longer installs anything.** The installed set is four artifacts
in `.identicon/` -- base64 for the transcript literal, a raster, a vector, and
the colour -- and the thing that writes them has to run in repositories that
have never heard of this one. That is the `repo-identicon` skill. What stays
here is the hook contract the tests exercise and the reasoning that produced
it.

Status: probe. Nothing is registered in `~/.claude/settings.json`, and the
`Stop` hook route below is recorded as rejected rather than merely unused.
"""

import base64
import importlib.util
import json
import os
import sys

# 4-pixel cells inside a 1-pixel border: 5*4 + 2*1. Superseded 30, which was
# reached by halving twice and had been seen in place; 22 is the first size
# that is both small enough beside a line of text and divides exactly, where 30
# leaves a stray pixel and sits fractionally off-centre.
SIZE = 22

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


# One directory rather than four root entries, so the SVG, the raster and the
# colour cost nothing at the top level. The naming Justin chose survives the
# move intact -- the prefix became the directory, the suffix the filename.
B64_NAME = ".identicon/png.b64"

# `$(cat ...)` strips the trailing newline, so the file can be a well-formed
# text file and the data URI still comes out clean.
HOOK_COMMAND = (
    """printf '{"systemMessage":"![](data:image/png;base64,%s)"}' """
    """"$(cat ${CLAUDE_PROJECT_DIR}/""" + B64_NAME + """)\""""
)


def payload_for(cwd):
    """The hook's entire stdout: the finished `systemMessage`, ready to print."""
    return json.dumps({"systemMessage": message_for(cwd)}, separators=(",", ":"))


def icon_for(cwd):
    """The identicon PNG. Rendered on demand; only its base64 is committed."""
    module = _identicon()
    key, _source = module.resolve_key(cwd)
    return module.render_png(key, SIZE)


def b64_for(cwd):
    """The committed artifact: base64 of the PNG, no wrapper, no newline.

    Stored rather than the PNG because the hook is the only consumer and it
    needs exactly this. Storing the image and re-encoding it every turn cost
    2.5ms to produce a file nothing else read -- measured, then removed.
    """
    return base64.b64encode(icon_for(cwd)).decode("ascii")


def settings_fragment():
    """A project-level hook that emits the identicon with no derivation at all.

    The identicon is a *constant* for a repository. Deriving it once per turn --
    a Python process, a module import and two git calls, 68ms measured -- to
    reproduce a string that cannot change is work for its own sake. Reading the
    finished string costs 2.4ms, and nothing can go wrong in between.

    What is stored is `repository-identicon-png.b64` in the repository root:
    base64 of the PNG, and nothing else. Not inside `settings.json`, because a
    219-character blob in hand-edited configuration makes every diff unreadable
    and invites breaking the icon while editing an unrelated hook. Not under
    `.claude/`, because an identicon identifies the *repository*, not this
    tool's use of it -- the hook lives there because a Claude Code hook
    genuinely is Claude Code's business, and the identifier does not.

    Not the PNG either, though that was tried. The hook is the only consumer,
    it needs the base64, and re-encoding an image every turn cost 2.5ms to
    maintain a file nothing else read. The name carries what the bytes are, so
    the encoding costs no clarity.

    `${CLAUDE_PROJECT_DIR}` rather than a relative path: hook commands resolve
    relative paths against the working directory, and the working directory can
    change mid-session. The placeholder is documented as surviving that.

    The hook is per-project because there is no global place a per-repository
    constant could live, and a user-level hook would have to rederive the key
    every turn just to learn which repository it was in, which is the entire
    cost being removed.

    It survives cloning, because the key is the git remote rather than a path
    (finding Q). The committed files are correct in every checkout of this
    repository, on any machine, which a path-keyed identicon could never manage.
    """
    return {
        "hooks": {
            "Stop": [{"hooks": [{"type": "command", "command": HOOK_COMMAND}]}]
        }
    }


# Installation used to live here. It does not any more: the installed set is
# four artifacts in `.identicon/` rather than one file, and the thing that
# writes them has to run in repositories that have never heard of this one. It
# is the `repo-identicon` skill, and this file would only be a second
# implementation of it, free to disagree.
INSTALLER = "/repo-identicon"


def main():
    if "--settings" in sys.argv:
        print(json.dumps(settings_fragment(), indent=2))
        return 0
    if "--payload" in sys.argv:
        print(payload_for(os.getcwd()))
        return 0
    if "--icon" in sys.argv:
        sys.stdout.buffer.write(icon_for(os.getcwd()))
        return 0
    if "--b64" in sys.argv:
        print(b64_for(os.getcwd()))
        return 0
    if "--install" in sys.argv:
        print(f"installation moved to the skill: {INSTALLER}", file=sys.stderr)
        return 2

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

# To give *another* repository an identicon, do not use this file. It only runs
# from a checkout of this repository, because it imports the full implementation
# by absolute path. Use the skill, which carries its own copy of the derivation
# and depends on nothing:
#
#   /repo-identicon              in a session opened on that repository
#   ~/.claude/skills/repo-identicon/repo-identicon.py [PATH]
#
# This file stays because it is where the mechanism was worked out and it is
# what the hook-contract tests above exercise. The two are held to each other by
# TestThePortableInstallerAgrees in tests/test_turn_identicon.py: the conformance
# apparatus -- the vendored identicon.js and its pinned vectors -- lives here, so
# this is the only place the comparison can be made.
#
# The generated literal survives cloning: the key is the git remote, not a path,
# so the committed files are correct in every checkout on every machine.
# Regenerate only if the remote changes or the spec does.
