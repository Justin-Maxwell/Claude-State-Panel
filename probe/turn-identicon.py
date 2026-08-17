#!/usr/bin/env python3
"""Emit the project identicon at the end of every turn, in every session.

Registered as a `Stop` hook. `Stop` fires on *every* response turn rather than
only on genuine completions -- the exact property that made it useless as a
"Claude is waiting for you" signal (see the exploration doc, section 1.1) is
the property this needs. The defect is the feature.

Output goes through `systemMessage`, which hooks deliver to the *user's*
transcript rather than to Claude. So it is deterministic: it does not depend
on the model choosing to comply, cannot be dropped under context pressure,
and costs no tokens.

The identicon is a PNG inlined as a `data:` URI in markdown image syntax,
because a monochrome text rendering throws away the colour, and the colour is
half the identity. Verified 2026-08-17: a markdown `data:image/png` renders in
the Claude Desktop chat. Roughly 200 bytes per icon, so the JSON stays small.

`--text` falls back to half-block characters for surfaces that render no
images. Verified in neither surface yet; see the note under `render_text`.

Identity is imported from the evaluator rather than reimplemented, so the
chat, the panel and `doctor` cannot disagree about what a project looks like.

Status: probe. Not registered anywhere. Registration snippet is at the bottom.
"""

import base64
import importlib.util
import json
import pathlib
import struct
import sys
import zlib

_EVALUATOR = pathlib.Path(__file__).resolve().parent.parent / "evaluator" / "claude-state-eval.py"

CELL = 6
QUIET = 0


def _project_identity(cwd):
    """Borrow the evaluator's derivation. One source of truth, or none."""
    spec = importlib.util.spec_from_file_location("_eval", _EVALUATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.project_identity(cwd)


def _chunk(kind, payload):
    body = kind + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def render_png(grid, colour):
    """RGBA PNG of the grid, transparent where a cell is off.

    Hand-rolled rather than via Pillow: a hook that every session runs on every
    turn should not be able to fail on a missing dependency. Transparent rather
    than white so the icon sits on whatever background the surface uses -- the
    chat is light here and dark elsewhere, and the saturated cells read on both.
    """
    red, green, blue = (int(colour[index:index + 2], 16) for index in (1, 3, 5))
    span = len(grid)
    size = (span + 2 * QUIET) * CELL
    scanlines = []
    for y in range(size):
        row_index = y // CELL - QUIET
        scanline = bytearray([0])
        for x in range(size):
            column = x // CELL - QUIET
            lit = 0 <= row_index < span and 0 <= column < span and grid[row_index][column] == "1"
            scanline += bytes((red, green, blue, 255)) if lit else bytes(4)
        scanlines.append(bytes(scanline))
    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", header)
            + _chunk(b"IDAT", zlib.compress(b"".join(scanlines), 9))
            + _chunk(b"IEND", b""))


def render_text(grid):
    """Three lines of half-block characters, for surfaces with no images.

    Two grid rows share one text line -- upper and lower half of one cell --
    because a terminal cell is about twice as tall as it is wide, and a naive
    one-line-per-row rendering comes out stretched to double width. This path
    loses the colour entirely, which is why it is the fallback and not the
    default.
    """
    lines = []
    for top in range(0, len(grid), 2):
        upper = grid[top]
        lower = grid[top + 1] if top + 1 < len(grid) else "0" * len(upper)
        line = ""
        for column in range(len(upper)):
            high, low = upper[column] == "1", lower[column] == "1"
            line += "█" if high and low else "▀" if high else "▄" if low else " "
        lines.append(line)
    return "\n".join(lines)


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    cwd = payload.get("cwd") or ""
    if not cwd:
        return 0

    try:
        colour, grid = _project_identity(cwd)
    except Exception:
        # A hook that fails must not disturb the session it is decorating.
        return 0

    if "--text" in sys.argv:
        message = render_text(grid)
    else:
        # Empty alt text: the icon is the whole message. A printed name beside
        # it is redundant when you already know which window you are looking
        # at, and it is the identicon that has to do the work.
        encoded = base64.b64encode(render_png(grid, colour)).decode("ascii")
        message = f"![](data:image/png;base64,{encoded})"

    print(json.dumps({"systemMessage": message}))
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
