#!/usr/bin/env python3
"""Emit the project identicon at the end of every turn, in every session.

Registered as a `Stop` hook. `Stop` fires on *every* response turn rather than
only on genuine completions -- the exact property that made it useless as a
"Claude is waiting for you" signal (see the exploration doc, section 1.1) is
the property this needs. The defect is the feature.

The identicon is emitted through `systemMessage`, which hooks deliver to the
*user's transcript* rather than to Claude. So the output is deterministic: it
does not depend on the model choosing to comply, cannot be dropped under
context pressure, and costs no tokens.

Identity is imported from the evaluator rather than reimplemented, so the
chat, the panel and `doctor` cannot disagree about what a project looks like.

Status: probe. Not registered anywhere. See the registration snippet at the
bottom of this file.
"""

import importlib.util
import json
import pathlib
import sys

_EVALUATOR = pathlib.Path(__file__).resolve().parent.parent / "evaluator" / "claude-state-eval.py"


def _project_identity(cwd):
    """Borrow the evaluator's derivation. One source of truth, or none."""
    spec = importlib.util.spec_from_file_location("_eval", _EVALUATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.project_identity(cwd)


def render(grid):
    """Five rows of "0"/"1" as three lines of half-block characters.

    Two grid rows share one text line -- upper half and lower half of the same
    cell -- because a terminal cell is roughly twice as tall as it is wide. A
    naive one-line-per-row rendering comes out stretched to twice its width.
    The fifth row has no partner and renders as upper halves alone.
    """
    lines = []
    for top in range(0, len(grid), 2):
        upper = grid[top]
        lower = grid[top + 1] if top + 1 < len(grid) else "0" * len(upper)
        line = ""
        for column in range(len(upper)):
            high = upper[column] == "1"
            low = lower[column] == "1"
            line += "█" if high and low else "▀" if high else "▄" if low else " "
        lines.append(line)
    return lines


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    cwd = payload.get("cwd") or ""
    if not cwd:
        return 0

    try:
        _colour, grid = _project_identity(cwd)
    except Exception:
        # A hook that fails must not disturb the session it is decorating.
        return 0

    label = pathlib.Path(cwd).name
    lines = render(grid)
    lines[0] = f"{lines[0]}  {label}"

    print(json.dumps({"systemMessage": "\n".join(lines)}))
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
