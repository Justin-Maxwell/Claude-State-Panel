#!/usr/bin/env python3
"""The identicon as two lines of text, for clients that render neither.

A terminal chat client shows an assistant message as plain markdown: the inline
PNG arrives as literal base64, and ANSI escapes are stripped before they reach
the terminal. What does survive is text -- including Unicode block glyphs and
colour emoji. This module renders an identicon into those two channels.

The output is two lines:

    <octant><octant><octant>
    <octant><octant><octant> <emoji><emoji><emoji>

Three octant characters by two lines carry the whole 5x5 grid, and the three
emoji carry the colour. The emoji terminate the mark on the lower line rather
than opening it on the upper one: an emoji is a full character cell tall, so
it sits flush beside a line that is full of grid, where beside the upper line
-- which is mostly the padding described at TOP_PAD -- it would float.

A blank sub-cell is SPACE -- U+0020 genuinely *is* the octant for the all-blank
pattern -- but it is emitted doubled, see BLANK, because it is the one
single-width character in the set. Each line is therefore three octant *cells*
and six columns, though not always three characters. The upper line is entirely
blank whenever the grid's top row is, roughly one repository in eight; it
carries no information in that case, but anything that strips trailing
whitespace still collapses the mark's height, so keep both lines intact.

**Both the octants and the emoji render double-width.** Checked against Konsole
with the fonts installed here, across the new astral octants, the inherited
block elements and the quadrants alike: all of them occupy two columns, and
SPACE occupies one, which is the whole reason BLANK doubles it. Treat this as
the normal case rather than a local quirk. A three-cell octant block is six
columns, exactly three emoji. Anything laying several marks out on one line
cannot assume one column per character, and single-width text interleaved with
them needs two spaces per glyph column to stay in step.

Two halves, two sets of reasoning.

**The grid, in octants.** Unicode 16.0 divides a character cell into 2x4
subcells, and a terminal cell is roughly twice as tall as it is wide, so an
octant subcell is square. A 5x5 grid at one subcell per cell therefore fits in
three characters by two lines and stays in proportion. The table below is
literal rather than computed, because the obvious construction is wrong: there
are **230** `BLOCK OCTANT-n` characters at U+1CD00-U+1CDE5, not 240, since 26
of the 256 patterns are encoded elsewhere under descriptive names -- the
sixteen quadrant-representable ones, four single top/bottom subcells, four
full-row blocks and two middle-row pairs. Deriving the codepoint by offset
arithmetic with the wrong exclusion set produces plausible, wrong glyphs, and
past U+1CDE5 it walks into pictograms: an early draft rendered
U+1CDED BOTTOM HALF LEFT-FACING RUNNER FRAME-1 into the middle of an identicon.
`selftest` re-derives the whole table from `unicodedata` where the host is
Unicode 16 or later, so the literal is checkable rather than merely asserted.

**The colour, in emoji.** A pure function of the colour: `#rrggbb` in, three
emoji out. Nothing else is consulted -- not the key, not the digest, not the
grid. Two projects sharing a colour share a triple, which is harmless, because
the grid is what carries identity.

The palette is anchored on the Unicode *names*, not on any font. LARGE BLUE
SQUARE is blue, so it is `#0000FF` here. The installed Noto Color Emoji paints
it Material Blue 700 `#1976D2`, and Apple, Twemoji and Windows differ again;
deriving the palette from whichever font is present would make the mapping
unstable across machines for no gain. A consequence worth having: every
canonical colour maps to three of its own square with no special case in the
code.

The nearest single colour is used twice. Choosing freely from all 165 mixtures
minimises error but reads badly, because the eye does not average three large
squares -- it reads the majority. Yellow-green `#d5d926` is closest to
RED YELLOW GREEN, a muddle; constraining it to YELLOW YELLOW BLACK costs 0.02
mean dE across the hue circle and is obviously yellow. Measured over the
identicon's 256 hues the constraint also shortens the longest run of a single
triple from 36 to 29 degrees, so legibility is not paid for in spread.

Averaging is in linear light, which is what optical mixing does, and compared
in Oklab, which is near enough perceptually uniform for Euclidean distance to
mean something. Fixed-lightness HSL, which the identicon draws its colour
from, is not, and clusters badly in the greens.

Standard library only.
"""

import math

# ---------------------------------------------------------------------------
# Octants
#
# Bit i of a pattern is subcell (row i // 2, col i % 2), rows top to bottom.
# Unicode numbers the octants 1..8 in that same order, so BLOCK OCTANT-247 is
# the pattern with bits 1, 3 and 6 set. Index this table by the pattern.
#
# Twenty-six of the 256 entries are inherited rather than new: the quadrants
# and block elements that already existed were not re-encoded when Unicode 16
# specified the set. They are the right characters and they are the right
# width, but they come from a far older design pass, and fonts commonly do not
# harmonise them with the 230 drawn in 2024 -- differing weight and coverage
# show as visible seams within a single rendered mark. Nothing on this side can
# fix that; it needs the fonts to redraw the old glyphs against the new set.
# Do not attempt to substitute lookalikes: for most of these patterns there is
# no alternative encoding at all.
# ---------------------------------------------------------------------------

OCTANTS = (
    " 𜺨𜺫🮂𜴀▘𜴁𜴂𜴃𜴄▝𜴅𜴆𜴇𜴈▀𜴉𜴊𜴋𜴌🯦𜴍𜴎𜴏𜴐𜴑𜴒𜴓𜴔𜴕𜴖𜴗"   #   0- 31
    "𜴘𜴙𜴚𜴛𜴜𜴝𜴞𜴟🯧𜴠𜴡𜴢𜴣𜴤𜴥𜴦𜴧𜴨𜴩𜴪𜴫𜴬𜴭𜴮𜴯𜴰𜴱𜴲𜴳𜴴𜴵🮅"   #  32- 63
    "𜺣𜴶𜴷𜴸𜴹𜴺𜴻𜴼𜴽𜴾𜴿𜵀𜵁𜵂𜵃𜵄▖𜵅𜵆𜵇𜵈▌𜵉𜵊𜵋𜵌▞𜵍𜵎𜵏𜵐▛"   #  64- 95
    "𜵑𜵒𜵓𜵔𜵕𜵖𜵗𜵘𜵙𜵚𜵛𜵜𜵝𜵞𜵟𜵠𜵡𜵢𜵣𜵤𜵥𜵦𜵧𜵨𜵩𜵪𜵫𜵬𜵭𜵮𜵯𜵰"   #  96-127
    "𜺠𜵱𜵲𜵳𜵴𜵵𜵶𜵷𜵸𜵹𜵺𜵻𜵼𜵽𜵾𜵿𜶀𜶁𜶂𜶃𜶄𜶅𜶆𜶇𜶈𜶉𜶊𜶋𜶌𜶍𜶎𜶏"   # 128-159
    "▗𜶐𜶑𜶒𜶓▚𜶔𜶕𜶖𜶗▐𜶘𜶙𜶚𜶛▜𜶜𜶝𜶞𜶟𜶠𜶡𜶢𜶣𜶤𜶥𜶦𜶧𜶨𜶩𜶪𜶫"   # 160-191
    "▂𜶬𜶭𜶮𜶯𜶰𜶱𜶲𜶳𜶴𜶵𜶶𜶷𜶸𜶹𜶺𜶻𜶼𜶽𜶾𜶿𜷀𜷁𜷂𜷃𜷄𜷅𜷆𜷇𜷈𜷉𜷊"   # 192-223
    "𜷋𜷌𜷍𜷎𜷏𜷐𜷑𜷒𜷓𜷔𜷕𜷖𜷗𜷘𜷙𜷚▄𜷛𜷜𜷝𜷞▙𜷟𜷠𜷡𜷢▟𜷣▆𜷤𜷥█"   # 224-255
)

GRID_SIZE = 5

# What to emit for the all-blank pattern. OCTANTS[0] is U+0020, which is
# correct -- SPACE genuinely is the character for that pattern -- but it is
# single-width where every other octant is double, so a blank in the middle of
# a line makes that line one column short and the mark visibly skews against
# the line below. Two ASCII spaces restore the column count. The table stays
# canonical; the compensation lives here, at the point of emission.
BLANK = "  "

# Sub-rows of blank above the grid. Two lines of octants are eight sub-rows and
# the grid is five, so there are three to spend; all three go above. That fills
# the lower line completely with grid, which is what lets the emoji sit flush
# against it, and it leaves the padding where it does the least harm -- the
# upper line holds only the grid's top row, so when that row is empty the line
# is blank but nothing is lost. Centring the grid instead (TOP_PAD 1 or 2)
# splits the padding but puts a partly-empty line under the emoji.
TOP_PAD = 3


def parse_grid(text):
    """A 5x5 grid from 25 characters, or from five rows separated by commas.

    Filled cells are `#`, `1`, `X` or `x`; anything else is empty.
    """
    rows = text.split(",") if "," in text else [
        text[i:i + GRID_SIZE] for i in range(0, len(text), GRID_SIZE)]
    if len(rows) != GRID_SIZE or any(len(r) != GRID_SIZE for r in rows):
        raise ValueError(f"not a {GRID_SIZE}x{GRID_SIZE} grid: {text!r}")
    return [[c in "#1Xx" for c in row] for row in rows]


def grid_lines(grid):
    """The grid as octant characters: three per line, two lines.

    One grid cell per subcell. Five columns need three characters (two
    subcolumns each) and five rows need two lines (four subrows each), with
    the grid pushed down by TOP_PAD; subcells outside the grid are empty.
    """
    def filled(row, col):
        return (0 <= row < GRID_SIZE and 0 <= col < GRID_SIZE
                and bool(grid[row][col]))

    lines = []
    for line in range((GRID_SIZE + TOP_PAD + 3) // 4):
        chars = []
        for cell in range((GRID_SIZE + 1) // 2):
            pattern = 0
            for bit in range(8):
                if filled(line * 4 + bit // 2 - TOP_PAD, cell * 2 + bit % 2):
                    pattern |= 1 << bit
            chars.append(BLANK if pattern == 0 else OCTANTS[pattern])
        lines.append("".join(chars))
    return lines


# ---------------------------------------------------------------------------
# The palette
#
# Unicode names each square by a colour word, and that word is the definition.
# Red, green and blue take the RGB primaries. Orange, purple and brown have no
# primary reading and take their CSS named-colour values.
# ---------------------------------------------------------------------------

PALETTE = (
    ("\U0001F7E5", "red",    0x1F7E5, (0xFF, 0x00, 0x00)),
    ("\U0001F7E7", "orange", 0x1F7E7, (0xFF, 0xA5, 0x00)),
    ("\U0001F7E8", "yellow", 0x1F7E8, (0xFF, 0xFF, 0x00)),
    ("\U0001F7E9", "green",  0x1F7E9, (0x00, 0xFF, 0x00)),
    ("\U0001F7E6", "blue",   0x1F7E6, (0x00, 0x00, 0xFF)),
    ("\U0001F7EA", "purple", 0x1F7EA, (0x80, 0x00, 0x80)),
    ("\U0001F7EB", "brown",  0x1F7EB, (0xA5, 0x2A, 0x2A)),
    ("⬛",     "black",  0x02B1B, (0x00, 0x00, 0x00)),
    ("⬜",     "white",  0x02B1C, (0xFF, 0xFF, 0xFF)),
)


def _linear(component):
    """One sRGB component, 0-255, to linear light."""
    c = component / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _encode(value):
    """Linear light back to one sRGB component, 0-255."""
    v = min(1.0, max(0.0, value))
    v = 12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055
    return int(v * 255 + 0.5)


def _oklab(linear_rgb):
    """Linear-light sRGB to Oklab. Bjorn Ottosson's matrices, unmodified."""
    r, g, b = linear_rgb
    long_ = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    med   = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    short = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    long_, med, short = (math.copysign(abs(v) ** (1 / 3), v)
                         for v in (long_, med, short))
    return (0.2104542553 * long_ + 0.7936177850 * med - 0.0040720468 * short,
            1.9779984951 * long_ - 2.4285922050 * med + 0.4505937099 * short,
            0.0259040371 * long_ + 0.7827717662 * med - 0.8086757660 * short)


_PALETTE_LINEAR = tuple(tuple(_linear(v) for v in rgb) for _, _, _, rgb in PALETTE)
_PALETTE_LAB = tuple(_oklab(lin) for lin in _PALETTE_LINEAR)


def _mix(indices):
    """Linear-light mean of the given palette entries."""
    return tuple(sum(_PALETTE_LINEAR[i][k] for i in indices) / len(indices)
                 for k in range(3))


def parse_hex(value):
    """`#rrggbb` or `rrggbb` to an (r, g, b) triple of 0-255 ints."""
    text = value.strip().lstrip("#")
    if len(text) != 6:
        raise ValueError(f"not a six-digit hex colour: {value!r}")
    return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))


def nearest_square(rgb):
    """Index into PALETTE of the single square closest to `rgb`.

    Ties break towards the lower index, so the choice is fixed rather than
    left to whatever `min` happens to do.
    """
    target = _oklab(tuple(_linear(v) for v in rgb))
    return min(range(len(PALETTE)),
               key=lambda i: (math.dist(_PALETTE_LAB[i], target), i))


def triple_indices(rgb):
    """The three PALETTE indices for `rgb`, ascending.

    The nearest single square twice, plus whichever third square brings the
    linear-light mean closest to the target. When the target *is* a palette
    colour the third is the base again, so canonical colours land on three of
    a kind without that being written down anywhere.
    """
    target = _oklab(tuple(_linear(v) for v in rgb))
    base = nearest_square(rgb)
    best, best_odd = None, None
    for odd in range(len(PALETTE)):
        distance = math.dist(_oklab(_mix((base, base, odd))), target)
        if best is None or distance < best:
            best, best_odd = distance, odd
    return tuple(sorted((base, base, best_odd)))


def emoji_triple(rgb):
    """The three emoji for `rgb`, as one string of three characters."""
    return "".join(PALETTE[i][0] for i in triple_indices(rgb))


def triple_names(rgb):
    """The three colour names for `rgb`, ascending by palette order."""
    return tuple(PALETTE[i][1] for i in triple_indices(rgb))


def triple_detail(rgb):
    """Everything about the choice, for tests and for explaining a result."""
    indices = triple_indices(rgb)
    mix = _mix(indices)
    target = _oklab(tuple(_linear(v) for v in rgb))
    return {
        "indices": indices,
        "emoji": "".join(PALETTE[i][0] for i in indices),
        "names": tuple(PALETTE[i][1] for i in indices),
        "base": PALETTE[nearest_square(rgb)][1],
        "mix_hex": "#{:02x}{:02x}{:02x}".format(*(_encode(v) for v in mix)),
        "delta_e": math.dist(_oklab(mix), target),
    }


# ---------------------------------------------------------------------------
# The whole mark
# ---------------------------------------------------------------------------

def blocktext(grid, rgb):
    """The identicon as two lines, the emoji terminating the lower one.

    See the module docstring for why the emoji go last rather than first, and
    for the double-width behaviour that matters when laying several of these
    out together.
    """
    lines = grid_lines(grid)
    lines[-1] = f"{lines[-1]} {emoji_triple(rgb)}"
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Self-check and demo
# ---------------------------------------------------------------------------

def selftest():
    """Invariants that hold for any palette and any Unicode 16 host."""
    assert len(OCTANTS) == 256, len(OCTANTS)
    assert len(set(OCTANTS)) == 256, "octant table has duplicates"

    # Re-derive the table from the Unicode database where the host has it, so
    # the literal above is verified rather than trusted.
    import unicodedata
    if tuple(int(p) for p in unicodedata.unidata_version.split(".")[:1]) >= (16,):
        named = 0
        for pattern, char in enumerate(OCTANTS):
            try:
                name = unicodedata.name(char)
            except ValueError:
                continue
            if not name.startswith("BLOCK OCTANT-"):
                continue
            named += 1
            bits = 0
            for digit in name[len("BLOCK OCTANT-"):]:
                bits |= 1 << (int(digit) - 1)
            assert bits == pattern, (name, pattern, bits)
        assert named == 230, f"expected 230 BLOCK OCTANT characters, saw {named}"

    # Every canonical colour is three of its own square, with no special case.
    for index, (char, name, _, rgb) in enumerate(PALETTE):
        detail = triple_detail(rgb)
        assert detail["indices"] == (index, index, index), (name, detail)
        assert detail["delta_e"] == 0.0, (name, detail["delta_e"])
        assert detail["emoji"] == char * 3, (name, detail["emoji"])

    # The majority constraint: some colour always appears at least twice.
    for value in range(0, 0x1000000, 0x3F1D7):
        indices = triple_indices(((value >> 16) & 0xFF,
                                  (value >> 8) & 0xFF, value & 0xFF))
        assert len(set(indices)) <= 2, indices

    # This repository, pinned at TOP_PAD = 3.
    if TOP_PAD == 3:
        grid = parse_grid(".#.#.,.#.#.,#...#,#.#.#,.#.#.")
        expected = ("\U0001CEA0\U0001CEA0  \n"
                    "\U0001CD86\U0001CD82\U0001FBE6 "
                    "\U0001F7E9\U0001F7E6\U0001F7E6")
        actual = blocktext(grid, parse_hex("#2692d9"))
        assert actual == expected, actual

    # The emoji terminate the mark: they are on the last line, not the first.
    mark = blocktext(parse_grid("#" * 25), parse_hex("#2692d9"))
    first, last = mark.split("\n")
    assert not any(p[0] in first for p in PALETTE), first
    assert last.endswith(emoji_triple(parse_hex("#2692d9"))), last

    # Whatever the padding or the pattern, the mark is two lines of three
    # octant cells, and every line is the same number of columns wide -- which
    # is the property BLANK exists to preserve. Blanks always come in pairs, so
    # cells can be counted directly.
    for shape in ("#" * 25, "." * 25, ".#.#.,#...#,.....,#...#,.#.#."):
        rendered = grid_lines(parse_grid(shape))
        assert len(rendered) == 2, rendered
        for line in rendered:
            assert line.count(" ") % 2 == 0, repr(line)
            cells = sum(1 for c in line if c != " ") + line.count(" ") // 2
            assert cells == 3, (repr(line), cells)
    return True


def _main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip().splitlines()[0])
        print("\nusage: identicon-blocktext.py --selftest")
        print("       identicon-blocktext.py <#rrggbb> <grid>")
        print("\n  <grid>  25 characters, or five rows separated by commas;")
        print("          `#`, `1`, `X` or `x` is a filled cell.")
        return 0
    if argv[0] == "--selftest":
        selftest()
        print("selftest: ok")
        return 0
    if len(argv) != 2:
        print("need a colour and a grid; --help for the spelling")
        return 2
    print(blocktext(parse_grid(argv[1]), parse_hex(argv[0])))
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(_main(sys.argv[1:]))
