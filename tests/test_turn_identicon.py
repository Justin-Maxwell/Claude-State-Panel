"""The chat-transcript hook, and the two things that decide how big it renders.

Rendered size is not ours to set. The client decides, and it decides from the
PNG's own dimensions -- verified 2026-08-17 by rendering the same identicon at
15x15 and 84x84 in one message: the small one sat inline in the text flow, the
large one was wrapped in a bordered card. Raw HTML is printed as literal text,
so `<img width>` cannot override it. Pixels are the only control there is.

So two things are pinned here: the emitted PNG is exactly 30x30, and the
message is a bare markdown image and nothing else. Both have been got wrong
already -- 30x30 was reached by halving twice, and a preview sent through a
file-card channel rendered oversized regardless of its pixels, which is what
prompted this file.
"""

import base64
import json
import os
import re
import struct
import subprocess
import unittest

import support

HOOK = support.REPO_ROOT / "probe" / "turn-identicon.py"
CWD = str(support.REPO_ROOT)

MARKDOWN_IMAGE = re.compile(r"^!\[\]\(data:image/png;base64,([A-Za-z0-9+/=]+)\)$")


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

    def test_the_image_is_thirty_by_thirty(self):
        """Justin chose this size against a rendered bracket. The client sizes
        from the PNG, so this number *is* the rendered size."""
        raw = self.png()
        self.assertEqual((30, 30), struct.unpack(">II", raw[16:24]))

    def test_it_is_a_valid_png(self):
        raw = self.png()
        self.assertEqual(b"\x89PNG\r\n\x1a\n", raw[:8])
        self.assertEqual(b"IEND\xaeB`\x82", raw[-8:])

    def test_a_directory_with_no_project_emits_nothing_rather_than_failing(self):
        """A hook that fails must not disturb the session it decorates."""
        result = emit(cwd="")
        self.assertEqual(0, result.returncode)
        self.assertEqual("", result.stdout.strip())


class TestTheBakedConstant(unittest.TestCase):
    """`.claude/settings.json` carries the identicon as a literal.

    The identicon is a constant for a repository, so deriving it every turn --
    a process, a module import and two git calls, 68ms measured -- reproduces a
    string that cannot change. The literal costs one printf, 2.3ms measured.

    A stored derivation is only safe if something checks it, which is the same
    bargain `identicon/vectors.json` makes. These tests are that check: if the
    reference is ever bumped, or the key rule changes, the committed literal
    goes stale and this fails rather than the panel and the chat quietly
    disagreeing.
    """

    SETTINGS = support.REPO_ROOT / ".claude" / "settings.json"
    ICON = support.REPO_ROOT / ".identicon.png"

    def hook_command(self):
        settings = json.loads(self.SETTINGS.read_text())
        entries = settings["hooks"]["Stop"]
        self.assertEqual(1, len(entries), "one Stop hook, or the icon prints twice")
        handlers = entries[0]["hooks"]
        self.assertEqual(1, len(handlers))
        return handlers[0]

    def test_the_hook_runs_no_interpreter_and_no_script(self):
        """The whole point. If this ever grows an interpreter again, the
        constant is being recomputed and the 68ms is back."""
        handler = self.hook_command()
        self.assertEqual("command", handler["type"])
        for forbidden in ("python", ".py", "git ", "claude-state-identicon"):
            self.assertNotIn(forbidden, handler["command"],
                             "the hook must derive nothing")

    def test_the_icon_is_stored_as_an_image_outside_dot_claude(self):
        """An identicon identifies the repository, not this tool's use of it.
        It belongs where Konsole, a README badge or anything else can pick it
        up. Only the hook is Claude Code's business, so only the hook is filed
        under .claude/."""
        self.assertTrue(self.ICON.exists(), f"{self.ICON.name} must be at the root")
        self.assertEqual(b"\x89PNG\r\n\x1a\n", self.ICON.read_bytes()[:8])
        self.assertFalse((support.REPO_ROOT / ".claude" / "identicon.json").exists(),
                         "the Claude-shaped payload file should be gone")

    def test_the_image_is_not_inlined_into_the_settings(self):
        """A base64 blob inside hand-edited configuration makes every diff
        unreadable and invites breaking the icon while editing another hook."""
        settings = self.SETTINGS.read_text()
        self.assertNotIn("iVBOR", settings, "the PNG itself must not be inlined")
        self.assertLess(len(settings), 400)

    def test_the_command_uses_portable_base64(self):
        """`base64 -w0` is GNU-only; BSD and macOS do not have it. The committed
        settings are cloned to machines this one knows nothing about."""
        command = self.hook_command()["command"]
        self.assertNotIn("-w0", command)
        self.assertIn("tr -d", command)

    def test_the_hook_path_survives_a_changed_working_directory(self):
        """Hook commands resolve relative paths against the working directory,
        and the working directory can change mid-session -- there is a
        CwdChanged event for exactly that. ${CLAUDE_PROJECT_DIR} is documented
        as surviving it; a relative path would not."""
        self.assertIn("${CLAUDE_PROJECT_DIR}", self.hook_command()["command"])
        emitted = subprocess.run(
            ["sh", "-c", self.hook_command()["command"]],
            capture_output=True, text=True, timeout=30, cwd="/",
            env={**os.environ, "CLAUDE_PROJECT_DIR": str(support.REPO_ROOT)},
        )
        self.assertEqual(0, emitted.returncode, emitted.stderr)
        self.assertEqual(json.loads(emit().stdout), json.loads(emitted.stdout))

    def test_the_stored_image_is_still_correct(self):
        """The committed PNG must be the one the current spec produces. If the
        reference is ever bumped this fails, instead of a stale icon sitting in
        the tree contradicting the README."""
        message = json.loads(emit().stdout)["systemMessage"]
        derived = base64.b64decode(MARKDOWN_IMAGE.match(message).group(1))
        self.assertEqual(derived, self.ICON.read_bytes(),
                         "the committed .identicon.png has drifted; regenerate "
                         "with: probe/turn-identicon.py --install")

    def test_the_generator_reproduces_both_committed_files(self):
        settings = subprocess.run(
            ["python3", str(HOOK), "--settings"], capture_output=True, text=True,
            timeout=30, cwd=str(support.REPO_ROOT),
        )
        self.assertEqual(0, settings.returncode, settings.stderr)
        self.assertEqual(json.loads(self.SETTINGS.read_text()),
                         json.loads(settings.stdout))

        icon = subprocess.run(
            ["python3", str(HOOK), "--icon"], capture_output=True,
            timeout=30, cwd=str(support.REPO_ROOT),
        )
        self.assertEqual(0, icon.returncode, icon.stderr)
        self.assertEqual(self.ICON.read_bytes(), icon.stdout)


if __name__ == "__main__":
    unittest.main()
