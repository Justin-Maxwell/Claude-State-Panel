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


if __name__ == "__main__":
    unittest.main()
