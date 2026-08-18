"""The chat-transcript hook, and the two things that decide how big it renders.

Rendered size is not ours to set. The client decides, and it decides from the
PNG's own dimensions -- verified 2026-08-17 by rendering the same identicon at
15x15 and 84x84 in one message: the small one sat inline in the text flow, the
large one was wrapped in a bordered card. Raw HTML is printed as literal text,
so `<img width>` cannot override it. Pixels are the only control there is.

So two things are pinned here: the emitted PNG is exactly 22x22, and the
message is a bare markdown image and nothing else. Both have been got wrong
already -- the size was reached by halving twice, and a preview sent through a
file-card channel rendered oversized regardless of its pixels, which is what
prompted this file.

22 supersedes 30, chosen against a rendered turn once 30 had been seen in
place. It is a 5x5 grid of 4-pixel cells inside a 1-pixel border, which is also
the arithmetic reason to prefer it: 30 leaves a stray pixel after the grid and
the border, so the mark sits fractionally off-centre; 22 divides exactly.
"""

import base64
import json
import os
import pathlib
import re
import struct
import subprocess
import unittest
import zlib

import support

HOOK = support.REPO_ROOT / "probe" / "turn-identicon.py"
CWD = str(support.REPO_ROOT)

# 5*4 + 2*1. Named once so the raster, the vector and the geometry checks below
# cannot be resized independently of each other.
SIZE = 22
CELL = 4
BORDER = 1

MARKDOWN_IMAGE = re.compile(r"^!\[\]\(data:image/png;base64,([A-Za-z0-9+/=]+)\)$")
MARKDOWN_IMAGE_ANYWHERE = re.compile(r"!\[\]\(data:image/png;base64,([A-Za-z0-9+/=]+)\)")


def emit(cwd=CWD):
    result = subprocess.run(
        [str(HOOK)], input=json.dumps({"cwd": cwd, "hook_event_name": "Stop"}),
        capture_output=True, text=True, timeout=30,
    )
    return result


class TestTheHookContract(unittest.TestCase):

    def test_it_emits_a_single_system_message_and_nothing_else(self):
        result = emit()
        self.assertEqual(0, result.returncode)
        payload = json.loads(result.stdout)
        self.assertEqual(["systemMessage"], list(payload))

    def test_the_message_is_a_bare_markdown_image(self):
        """No caption, no alt text, no code fence, no surrounding prose. Alt
        text would print if the image failed, and anything fenced renders as a
        block rather than inline."""
        message = json.loads(emit().stdout)["systemMessage"]
        self.assertRegex(message, MARKDOWN_IMAGE)

    def test_the_payload_stays_small(self):
        """It is emitted on every turn of every session. A budget stops a future
        size change from quietly costing a kilobyte a turn."""
        self.assertLess(len(emit().stdout), 512)


class TestRenderedSizeIsPinned(unittest.TestCase):

    def png(self):
        message = json.loads(emit().stdout)["systemMessage"]
        return base64.b64decode(MARKDOWN_IMAGE.match(message).group(1))

    def test_the_image_is_twenty_two_by_twenty_two(self):
        """Justin chose this size against a rendered turn. The client sizes
        from the PNG, so this number *is* the rendered size."""
        raw = self.png()
        self.assertEqual((SIZE, SIZE), struct.unpack(">II", raw[16:24]))
        self.assertEqual(SIZE, 5 * CELL + 2 * BORDER)


    def test_it_is_a_valid_png(self):
        raw = self.png()
        self.assertEqual(b"\x89PNG\r\n\x1a\n", raw[:8])
        self.assertEqual(b"IEND\xaeB`\x82", raw[-8:])

    def test_a_directory_with_no_project_emits_nothing_rather_than_failing(self):
        """A hook that fails must not disturb the session it decorates."""
        result = emit(cwd="")
        self.assertEqual(0, result.returncode)
        self.assertEqual("", result.stdout.strip())


class TestTheCommittedInstruction(unittest.TestCase):
    """CLAUDE.md carries the identicon as a literal, and is the delivery path.

    Finding V killed the hook route: a `systemMessage` arrives as plain text
    with the event name prefixed to every line, and no hook output field can
    display an image. The only channel that renders markdown in a GUI chat
    client is an assistant message, and only the model writes those. So the
    mechanism is an instruction, which is honest about depending on compliance
    rather than pretending to a determinism the rendering channel cannot honour.

    A stored derivation is only safe if something checks it -- the same bargain
    `identicon/vectors.json` makes. These tests are that check.
    """

    INSTRUCTIONS = support.REPO_ROOT / "CLAUDE.md"
    ARTIFACT = support.REPO_ROOT / ".identicon" / "repository-identicon.png"

    def literal(self):
        found = MARKDOWN_IMAGE_ANYWHERE.findall(self.INSTRUCTIONS.read_text())
        self.assertEqual(1, len(found),
                         "exactly one identicon literal, or they can disagree")
        return found[0]

    def test_the_instruction_exists_and_carries_one_literal(self):
        self.assertTrue(self.INSTRUCTIONS.exists())
        self.assertRegex(self.INSTRUCTIONS.read_text(),
                         r"(?i)last line of every response")

    def test_the_literal_matches_the_committed_artifact(self):
        """The literal is base64 of the committed PNG, derived here rather than
        compared against a stored copy. There used to be a `.b64` file holding
        exactly these characters; it was a second copy of one image, free to
        disagree with the first, and was dropped once a real PNG existed to
        derive it from."""
        self.assertEqual(base64.b64encode(self.ARTIFACT.read_bytes()).decode("ascii"),
                         self.literal())

    def test_the_literal_matches_a_fresh_derivation(self):
        message = json.loads(emit().stdout)["systemMessage"]
        self.assertEqual(MARKDOWN_IMAGE.match(message).group(1), self.literal(),
                         "CLAUDE.md has drifted; regenerate with: "
                         "/repo-identicon")

    def test_no_hook_is_registered_for_this(self):
        """The hook route is not merely unused, it is removed. Leaving it
        registered would print `Stop says: ![](data:...)` under every turn."""
        settings = support.REPO_ROOT / ".claude" / "settings.json"
        if settings.exists():
            self.assertNotIn("identicon", settings.read_text())

    def test_the_committed_artifact_is_a_png(self):
        self.assertEqual(b"\x89PNG\r\n\x1a\n", self.ARTIFACT.read_bytes()[:8])


class TestTheArtifactSetAgreesWithItself(unittest.TestCase):
    """One mark, several files. Nothing outside this suite would ever notice
    them diverging, because each has a different consumer and no consumer reads
    two.

    That is exactly the shape of the failure this repository has already had
    once: a write path correct in storage and unusable end to end, green for
    four minor versions because nothing read it back. So each artifact is read
    back here, through the same door its real consumer uses -- the SVG gets its
    geometry compared against the raster's pixels, and the colour is checked
    against what is actually painted.

    Each filename repeats the directory deliberately. The directory is context,
    and context does not survive a file being copied out or fetched from a raw
    URL; `icon.png` on a desktop says nothing, where this still does.
    """

    DIRECTORY = support.REPO_ROOT / ".identicon"
    STEM = "repository-identicon"
    PNG = DIRECTORY / f"{STEM}.png"
    SVG = DIRECTORY / f"{STEM}.svg"
    COLOUR = DIRECTORY / f"{STEM}.colour"

    def opaque_pixels(self):
        """{(x, y): (r, g, b)} for every non-transparent pixel of the PNG.

        Decoded rather than trusted: this is the only place the committed image
        is read as an image rather than as bytes.
        """
        raw = self.PNG.read_bytes()
        width, height = struct.unpack(">II", raw[16:24])
        offset, compressed = 8, b""
        while offset < len(raw):
            length = struct.unpack(">I", raw[offset:offset + 4])[0]
            if raw[offset + 4:offset + 8] == b"IDAT":
                compressed += raw[offset + 8:offset + 8 + length]
            offset += 12 + length
        data = zlib.decompress(compressed)
        stride = width * 4
        pixels = {}
        for y in range(height):
            self.assertEqual(0, data[y * (stride + 1)], "unexpected PNG filter")
            row = data[y * (stride + 1) + 1:(y + 1) * (stride + 1)]
            for x in range(width):
                red, green, blue, alpha = row[x * 4:x * 4 + 4]
                if alpha:
                    pixels[(x, y)] = (red, green, blue)
        return pixels

    def test_every_artifact_is_present(self):
        for path in (self.PNG, self.SVG, self.COLOUR):
            self.assertTrue(path.exists(), f"{path} is missing")

    def test_no_superseded_artifact_survives_beside_its_replacement(self):
        """Carrying both leaves every consumer guessing which is current, and
        the stale one goes on looking authoritative forever."""
        for stale in ("png.b64", "icon.png", "icon.svg", "colour"):
            self.assertFalse((self.DIRECTORY / stale).exists(),
                             f"{stale} was superseded but is still here")

    def test_the_svg_covers_exactly_the_pixels_the_png_paints(self):
        """Same mark, not merely the same pattern -- the margin has to match
        too, or the two renderings look different side by side."""
        rects = re.findall(r'x="(\d+)" y="(\d+)" width="(\d+)" height="(\d+)"',
                           self.SVG.read_text())
        self.assertTrue(rects, "the SVG paints nothing")
        covered = {(int(x) + dx, int(y) + dy)
                   for x, y, w, h in rects
                   for dx in range(int(w)) for dy in range(int(h))}
        self.assertEqual(set(self.opaque_pixels()), covered)

    def test_the_colour_is_what_the_renderings_actually_paint(self):
        colour = self.COLOUR.read_text().strip()
        self.assertRegex(colour, r"^#[0-9a-f]{6}$",
                         "one form only, so a consumer never has to parse it")
        painted = {"#{:02x}{:02x}{:02x}".format(*rgb)
                   for rgb in self.opaque_pixels().values()}
        self.assertEqual({colour}, painted)
        self.assertEqual({colour},
                         set(re.findall(r'fill="(#[0-9a-f]{6})"', self.SVG.read_text())))

    def test_the_grid_is_four_pixel_cells_inside_a_one_pixel_border(self):
        """22 is not a bare number, it is 5*4 + 2*1, and the decomposition is
        the part that matters: a size that merely fits leaves a remainder and
        pushes the mark off-centre. Read out of the image rather than asserted
        against the constant, so it is the pixels being checked and not the
        arithmetic restating itself.
        """
        painted = self.opaque_pixels()
        self.assertTrue(painted, "the PNG paints nothing")
        xs = {x for x, _ in painted}
        ys = {y for _, y in painted}

        # The border means nothing is painted in the outermost rows or columns.
        self.assertGreaterEqual(min(xs | ys), BORDER)
        self.assertLessEqual(max(xs | ys), SIZE - BORDER - 1)

        # Whole cells means every cell is painted entirely or not at all, in
        # both axes. A partial cell is what a size with a remainder produces.
        starts = range(BORDER, BORDER + 5 * CELL, CELL)
        for row in sorted(ys):
            columns = {x for x, y in painted if y == row}
            for start in starts:
                self.assertIn(len(columns & set(range(start, start + CELL))),
                              (0, CELL),
                              f"row {row} paints a partial cell at x={start}")
        for column in sorted(xs):
            rows = {y for x, y in painted if x == column}
            for start in starts:
                self.assertIn(len(rows & set(range(start, start + CELL))),
                              (0, CELL),
                              f"column {column} paints a partial cell at y={start}")

    def test_each_text_artifact_ends_with_exactly_one_newline(self):
        """So each is a well-formed text file and `$(cat ...)` still yields it
        clean -- the shell strips exactly one."""
        for path in (self.SVG, self.COLOUR):
            text = path.read_text()
            self.assertTrue(text.endswith("\n"), f"{path} has no trailing newline")
            self.assertFalse(text.endswith("\n\n"), f"{path} has a blank line at the end")

    def test_the_superseded_root_artifact_is_gone(self):
        """Carrying both leaves every consumer guessing which is current."""
        self.assertFalse((support.REPO_ROOT / "repository-identicon-png.b64").exists())


def _find_portable_installer():
    """The `repo-identicon` script, wherever it currently lives.

    It has moved once already -- from a personal skill under `~/.claude` into
    the `Claude-Colophon` plugin repository -- and the move was invisible here,
    because a test that cannot find its subject skips, and a skip reads exactly
    like a pass in a green run. Hence a list of candidates and, below, a check
    that the list is not merely stale.
    """
    for candidate in (
        pathlib.Path.home() / "Code" / "Projects" / "Claude-Colophon"
        / "skills" / "repo-identicon" / "repo-identicon.py",
        pathlib.Path.home() / ".claude" / "skills" / "repo-identicon"
        / "repo-identicon.py",
    ):
        if candidate.exists():
            return candidate
    return None


PORTABLE_INSTALLER = _find_portable_installer()

# Where the plugin lives when it is checked out at all. Its presence is what
# separates "this machine never had it" from "it moved and nothing noticed".
PLUGIN_ROOT = pathlib.Path.home() / "Code" / "Projects" / "Claude-Colophon"


class TestTheConformanceCheckCanStillFindItsSubject(unittest.TestCase):
    """Guards the guard.

    The conformance tests below skip when the script is absent, which is right
    on a machine that never had it and wrong on one where it merely moved. A
    skip is indistinguishable from a pass in a green run, so the one case that
    can be told apart is asserted here: if the plugin is checked out, its script
    has to be where this file expects it.
    """

    @unittest.skipUnless(PLUGIN_ROOT.exists(),
                         f"{PLUGIN_ROOT} is not checked out here")
    def test_the_plugin_is_checked_out_so_the_script_must_be_found(self):
        self.assertIsNotNone(
            PORTABLE_INSTALLER,
            f"{PLUGIN_ROOT} exists but no repo-identicon script was found; the "
            "conformance tests below are silently skipping. Update "
            "_find_portable_installer().")


@unittest.skipUnless(PORTABLE_INSTALLER,
                     "the repo-identicon script is not on this machine")
class TestThePortableInstallerAgrees(unittest.TestCase):
    """The `repo-identicon` skill carries its own copy of the derivation.

    It has to. It installs an identicon into any repository, and shipping this
    repository's conformance apparatus -- the vendored identicon.js and its
    pinned vectors -- alongside it would mean carrying a test suite in order to
    compute a string that never changes. So the vectors stay here, and this is
    where the two implementations are held to each other.

    The check is cheap because this repository is itself a repository with an
    identicon: if the portable script derives the same bytes for this project
    that the full implementation does, on a real remote-derived key, the two
    agree where it counts. It is machine-local, hence the skip -- a checkout on
    a machine without the skill installed has nothing to compare against and
    should not fail for it.
    """

    def portable_b64(self):
        result = subprocess.run(
            ["python3", str(PORTABLE_INSTALLER), str(support.REPO_ROOT), "--b64"],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        return result.stdout.strip()

    def test_it_derives_the_same_identicon_as_the_full_implementation(self):
        message = json.loads(emit().stdout)["systemMessage"]
        self.assertEqual(MARKDOWN_IMAGE.match(message).group(1),
                         self.portable_b64(),
                         "the portable installer has drifted from "
                         "identicon/claude-state-identicon.py")

    def test_it_resolves_the_same_key_from_the_same_remote(self):
        """Agreeing on the pixels is worth little if they came from a key the
        two would resolve differently in some other repository."""
        module = support.load_script(support.IDENTICON, "claude_state_identicon")
        expected, source = module.resolve_key(str(support.REPO_ROOT))
        result = subprocess.run(
            ["python3", str(PORTABLE_INSTALLER), str(support.REPO_ROOT), "--key"],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(f"{expected}\t{source}", result.stdout.strip())

    def portable(self, flag):
        result = subprocess.run(
            ["python3", str(PORTABLE_INSTALLER), str(support.REPO_ROOT), flag],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        return result.stdout

    def test_it_derives_the_same_colour_and_vector_as_the_full_implementation(self):
        """The other three artifacts need holding to the reference too, not
        just the raster the chat transcript happens to use."""
        module = support.load_script(support.IDENTICON, "claude_state_identicon")
        key, _source = module.resolve_key(str(support.REPO_ROOT))
        self.assertEqual(module.hex_colour(module.identicon_colour(key)),
                         self.portable("--colour").strip())
        self.assertEqual(module.render_svg(key, SIZE), self.portable("--svg"))

    def test_it_writes_nothing_when_asked_only_to_derive(self):
        """The read-only flags are what the test suite and a curious user reach
        for; either silently installing would be a nasty surprise."""
        before = {path: path.read_bytes() for path in
                  (self.ARTIFACT, self.INSTRUCTIONS) if path.exists()}
        self.portable_b64()
        for path, content in before.items():
            self.assertEqual(content, path.read_bytes())

    ARTIFACT = support.REPO_ROOT / ".identicon" / "repository-identicon.png"
    INSTRUCTIONS = support.REPO_ROOT / "CLAUDE.md"


if __name__ == "__main__":
    unittest.main()
