"""Complete 2x4 octant table, derived from unicodedata rather than assumed.

PROVENANCE ONLY. Nothing imports this. The table it produces is inlined in
identicon/mosaic-identicon.py, whose selftest re-derives and checks it
against unicodedata directly; this script is kept as the record of how that
table was worked out, and of the mistake it exists to prevent -- assuming the
octants were 240 characters at U+1CD00 rather than 230 at U+1CD00-U+1CDE5,
which produced valid-looking wrong glyphs and, past U+1CDE5, ran into
pictograms.


Bit i of a pattern is subcell (row i//2, col i%2), rows top-to-bottom.
Unicode names octants 1..8 in the same order, so the 230 BLOCK OCTANT-n
characters decode directly.  The other 26 patterns are encoded elsewhere
under descriptive names; each is asserted below so a wrong guess fails loudly.
"""
import unicodedata as ud

TABLE = {}
for _cp in range(0x1CD00, 0x1CDE6):
    _nm = ud.name(chr(_cp))
    assert _nm.startswith("BLOCK OCTANT-"), _nm
    _bits = 0
    for _d in _nm[len("BLOCK OCTANT-"):]:
        _bits |= 1 << (int(_d) - 1)
    TABLE[_bits] = chr(_cp)
assert len(TABLE) == 230, len(TABLE)

# The 26 patterns with no BLOCK OCTANT name: (pattern, codepoint, expected name)
_EXTRA = [
    (0,   0x00020, "SPACE"),
    (1,   0x1CEA8, "LEFT HALF UPPER ONE QUARTER BLOCK"),
    (2,   0x1CEAB, "RIGHT HALF UPPER ONE QUARTER BLOCK"),
    (3,   0x1FB82, "UPPER ONE QUARTER BLOCK"),
    (5,   0x02598, "QUADRANT UPPER LEFT"),
    (10,  0x0259D, "QUADRANT UPPER RIGHT"),
    (15,  0x02580, "UPPER HALF BLOCK"),
    (20,  0x1FBE6, "MIDDLE LEFT ONE QUARTER BLOCK"),
    (40,  0x1FBE7, "MIDDLE RIGHT ONE QUARTER BLOCK"),
    (63,  0x1FB85, "UPPER THREE QUARTERS BLOCK"),
    (64,  0x1CEA3, "LEFT HALF LOWER ONE QUARTER BLOCK"),
    (80,  0x02596, "QUADRANT LOWER LEFT"),
    (85,  0x0258C, "LEFT HALF BLOCK"),
    (90,  0x0259E, "QUADRANT UPPER RIGHT AND LOWER LEFT"),
    (95,  0x0259B, "QUADRANT UPPER LEFT AND UPPER RIGHT AND LOWER LEFT"),
    (128, 0x1CEA0, "RIGHT HALF LOWER ONE QUARTER BLOCK"),
    (160, 0x02597, "QUADRANT LOWER RIGHT"),
    (165, 0x0259A, "QUADRANT UPPER LEFT AND LOWER RIGHT"),
    (170, 0x02590, "RIGHT HALF BLOCK"),
    (175, 0x0259C, "QUADRANT UPPER LEFT AND UPPER RIGHT AND LOWER RIGHT"),
    (192, 0x02582, "LOWER ONE QUARTER BLOCK"),
    (240, 0x02584, "LOWER HALF BLOCK"),
    (245, 0x02599, "QUADRANT UPPER LEFT AND LOWER LEFT AND LOWER RIGHT"),
    (250, 0x0259F, "QUADRANT UPPER RIGHT AND LOWER LEFT AND LOWER RIGHT"),
    (252, 0x02586, "LOWER THREE QUARTERS BLOCK"),
    (255, 0x02588, "FULL BLOCK"),
]
for _pat, _cp, _want in _EXTRA:
    assert _pat not in TABLE, f"pattern {_pat} already an octant"
    if _cp != 0x20:
        assert ud.name(chr(_cp)) == _want, (hex(_cp), ud.name(chr(_cp)), _want)
    TABLE[_pat] = chr(_cp)
assert len(TABLE) == 256 and all(n in TABLE for n in range(256))


def render(on, w, h):
    """`on(y, x) -> bool` over a w by h subcell field; returns list of lines."""
    out = []
    for cr in range(-(-h // 4)):
        out.append("".join(
            TABLE[sum(1 << i for i in range(8)
                      if on(cr * 4 + i // 2, cc * 2 + i % 2))]
            for cc in range(-(-w // 2))))
    return out
