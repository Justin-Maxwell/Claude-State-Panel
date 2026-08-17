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

Status: probe. Not registered anywhere. Registration snippet is at the bottom.
"""

import base64
import importlib.util
import json
import os
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


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    cwd = payload.get("cwd") or ""
    if not cwd:
        return 0

    try:
        module = _identicon()
        key, _source = module.resolve_key(cwd)
        png = module.render_png(key, SIZE)
    except Exception:
        # A hook that fails must not disturb the session it is decorating.
        return 0

    # Empty alt text: the icon is the whole message. A printed name beside it is
    # redundant when you already know which window you are looking at, and it is
    # the identicon that has to do the work.
    encoded = base64.b64encode(png).decode("ascii")
    print(json.dumps({"systemMessage": f"![](data:image/png;base64,{encoded})"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())

# Registration -- NOT installed. Add to ~/.claude/settings.json:
#
#   "hooks": {
#     "Stop": [
#       {
#         "hooks": [
#           {
#             "type": "command",
#             "command": "~/Code/Projects/Claude-State-Panel/probe/turn-identicon.py"
#           }
#         ]
#       }
#     ]
#   }
