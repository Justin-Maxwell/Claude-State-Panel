"""Extract the flat fill colour of each colour-square emoji from the installed
Noto Color Emoji, then pick the multiset of three whose optical average is
closest to a target colour in Oklab.

PROVENANCE ONLY. Nothing imports this, and it needs fontTools, which the rest
of the project does not. It is kept because it settled the question it was
written to answer, and settled it the other way: the installed Noto paints the
squares in Material Design colours -- blue is #1976D2, not #0000FF -- and every
other vendor differs again, so identicon-blocktext.py anchors its palette on
the Unicode *names* and ignores the font entirely. The extraction is also a
worked example of reading a COLRv1 paint graph: the face colour is not the
first or last solid but the layer with the greatest net visible area, since
later layers paint over earlier ones.
"""
import itertools, math
from fontTools.ttLib import TTFont

FONT = "/usr/share/fonts/google-noto-color-emoji-fonts/Noto-COLRv1.ttf"

SQUARES = [
    ("\U0001F7E5", "red"),    ("\U0001F7E7", "orange"), ("\U0001F7E8", "yellow"),
    ("\U0001F7E9", "green"),  ("\U0001F7E6", "blue"),   ("\U0001F7EA", "purple"),
    ("\U0001F7EB", "brown"),  ("⬛", "black"),      ("⬜", "white"),
]


def font_palette():
    """Each square is PaintColrLayers over PaintGlyph/PaintSolid pairs, painted
    back to front: border, face, highlight. Pick the layer with the greatest
    *net visible* area, i.e. its own area less everything drawn over it."""
    f = TTFont(FONT)
    cmap = f.getBestCmap()
    cpal = f["CPAL"].palettes[0]
    colr = f["COLR"].table
    layers = colr.LayerList
    glyf = f["glyf"]
    base = {r.BaseGlyph: r.Paint for r in colr.BaseGlyphList.BaseGlyphPaintRecord}

    def area(gname):
        g = glyf[gname]
        if g.numberOfContours == 0:
            return 0
        g.recalcBounds(glyf)
        return (g.xMax - g.xMin) * (g.yMax - g.yMin)

    def flatten(paint, out):
        """Paint order, back to front, as (area, paletteIndex) pairs."""
        fmt = paint.Format
        if fmt == 1:                                   # PaintColrLayers
            for i in range(paint.FirstLayerIndex,
                           paint.FirstLayerIndex + paint.NumLayers):
                flatten(layers.Paint[i], out)
        elif fmt == 10:                                # PaintGlyph
            inner = paint.Paint
            while inner.Format not in (2, 1):          # step past transforms
                inner = inner.Paint
            if inner.Format == 2:
                out.append((area(paint.Glyph), inner.PaletteIndex))
            else:
                flatten(inner, out)
        elif hasattr(paint, "Paint"):
            flatten(paint.Paint, out)
        return out

    out = []
    for ch, name in SQUARES:
        stack = flatten(base[cmap[ord(ch)]], [])
        assert stack, name
        net = [a - sum(b for b, _ in stack[i + 1:]) for i, (a, _) in enumerate(stack)]
        pick = max(range(len(stack)), key=lambda i: net[i])
        c = cpal[stack[pick][1]]
        out.append((ch, name, (c.red, c.green, c.blue), pick, len(stack)))
    picks = {p for _, _, _, p, _ in out}
    assert len(picks) == 1, f"face layer differs across squares: {picks}"
    return out


def srgb_to_linear(c):
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def oklab(lin):
    r, g, b = lin
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l, m, s = (math.copysign(abs(v) ** (1 / 3), v) for v in (l, m, s))
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def choose_triple(target_rgb, palette):
    """Deterministic: exhaustive over combinations_with_replacement in palette
    order, minimising Oklab distance; ties broken by the first index tuple."""
    tgt = oklab(tuple(srgb_to_linear(v) for v in target_rgb))
    lin = [tuple(srgb_to_linear(v) for v in p[2]) for p in palette]
    scored = []
    for combo in itertools.combinations_with_replacement(range(len(palette)), 3):
        avg = tuple(sum(lin[i][k] for i in combo) / 3 for k in range(3))
        lab = oklab(avg)
        d = math.dist(lab, tgt)
        scored.append((d, combo, avg))
    scored.sort(key=lambda t: (t[0], t[1]))
    return tgt, scored


def linear_to_srgb(c):
    c = max(0.0, min(1.0, c))
    v = 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
    return round(v * 255)


if __name__ == "__main__":
    pal = font_palette()
    print("--- palette read from", FONT.rsplit("/", 1)[-1], "---")
    for ch, name, rgb, pick, n in pal:
        print(f"  {ch}  {name:7s} #{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}   "
              f"(face = layer {pick} of {n})")

    target = (0x26, 0x92, 0xD9)
    tgt, scored = choose_triple(target, pal)
    print(f"\ntarget #2692D9  Oklab {tuple(round(v,4) for v in tgt)}")
    print("\n--- best 6 triples ---")
    for d, combo, avg in scored[:6]:
        chars = "".join(pal[i][0] for i in combo)
        names = "+".join(pal[i][1] for i in combo)
        hexa = "#%02X%02X%02X" % tuple(linear_to_srgb(v) for v in avg)
        print(f"  {chars}  dE={d:.4f}  avg {hexa}  {names}")
