"""Plasmoid package tests. Phase 2.

No Plasma shell is started here. These check the things that can be checked
without one -- and in particular they enforce the property the whole
architecture rests on: the QML is a renderer, and every field it reads must be
one the evaluator actually emits.

That last check is the one with teeth. "The panel and `doctor` cannot disagree"
is only true while the panel reads the evaluator's model and nothing else; a
typo'd or invented field name is exactly how that guarantee rots, and it would
otherwise show up as a blank column in a live panel rather than as a failure.

Whether the widget *looks* right is not testable here and is not claimed to be.
"""

import json
import pathlib
import re
import unittest
import xml.etree.ElementTree as ET

import support

evaluator = support.load_evaluator()

PLASMOID = support.REPO_ROOT / "plasmoid"
MAIN_QML = PLASMOID / "contents" / "ui" / "main.qml"
CONFIG_XML = PLASMOID / "contents" / "config" / "main.xml"
METADATA = PLASMOID / "metadata.json"

KCFG_NS = "{http://www.kde.org/standards/kcfg/1.0}"


def model():
    return evaluator.evaluate(support.agents("mixed"), now=1786836400.0, slots=4)


class TestPackageStructure(unittest.TestCase):
    def test_required_files_exist(self):
        for path in (METADATA, MAIN_QML, CONFIG_XML,
                     PLASMOID / "contents" / "config" / "config.qml",
                     PLASMOID / "contents" / "ui" / "ConfigGeneral.qml"):
            with self.subTest(path=path.name):
                self.assertTrue(path.exists(), f"missing {path}")

    def test_metadata_is_valid_json_and_declares_plasma_6(self):
        meta = json.loads(METADATA.read_text())
        self.assertEqual("Plasma/Applet", meta["KPackageStructure"])
        self.assertIn("X-Plasma-API-Minimum-Version", meta)
        self.assertTrue(meta["KPlugin"]["Id"])

    def test_declared_licence_matches_the_repo(self):
        meta = json.loads(METADATA.read_text())
        self.assertEqual("AGPL-3.0-or-later", meta["KPlugin"]["License"])

    def test_plasmoid_id_matches_the_justfile(self):
        meta = json.loads(METADATA.read_text())
        justfile = (support.REPO_ROOT / "justfile").read_text()
        self.assertIn(meta["KPlugin"]["Id"], justfile,
                      "justfile uninstall recipe would target the wrong id")


class TestConfigSchema(unittest.TestCase):
    def test_config_xml_parses(self):
        ET.parse(CONFIG_XML)

    def test_no_double_hyphen_inside_an_xml_comment(self):
        """XML forbids it, and kpackagetool's failure message is not obvious.
        Writing `--json` in a comment is the easy way to hit this."""
        for body in re.findall(r"<!--(.*?)-->", CONFIG_XML.read_text(), re.S):
            self.assertNotIn("--", body, f"double hyphen in comment: {body[:60]!r}")

    def test_every_entry_has_a_default(self):
        root = ET.parse(CONFIG_XML).getroot()
        for entry in root.iter(f"{KCFG_NS}entry"):
            with self.subTest(entry=entry.get("name")):
                self.assertIsNotNone(entry.find(f"{KCFG_NS}default"))

    def test_numeric_defaults_sit_inside_their_own_bounds(self):
        root = ET.parse(CONFIG_XML).getroot()
        for entry in root.iter(f"{KCFG_NS}entry"):
            if entry.get("type") != "Int":
                continue
            with self.subTest(entry=entry.get("name")):
                value = int(entry.find(f"{KCFG_NS}default").text)
                low = entry.find(f"{KCFG_NS}min")
                high = entry.find(f"{KCFG_NS}max")
                if low is not None:
                    self.assertGreaterEqual(value, int(low.text))
                if high is not None:
                    self.assertLessEqual(value, int(high.text))

    def test_config_keys_have_a_matching_alias_in_the_config_page(self):
        """KCM binds by `cfg_<name>`; a mismatch silently ignores the setting."""
        root = ET.parse(CONFIG_XML).getroot()
        page = (PLASMOID / "contents" / "ui" / "ConfigGeneral.qml").read_text()
        for entry in root.iter(f"{KCFG_NS}entry"):
            with self.subTest(entry=entry.get("name")):
                self.assertIn(f"cfg_{entry.get('name')}", page)

    def test_qml_reads_only_declared_config_keys(self):
        declared = {e.get("name") for e in
                    ET.parse(CONFIG_XML).getroot().iter(f"{KCFG_NS}entry")}
        used = set(re.findall(r"Plasmoid\.configuration\.(\w+)", MAIN_QML.read_text()))
        self.assertEqual(set(), used - declared,
                         f"QML reads undeclared config keys: {used - declared}")


class TestPanelDocking(unittest.TestCase):
    """A panel fixes the applet's cross axis and asks for the main axis.

    Constraining only minimums, or leaving an axis at zero, produces an applet
    that collapses to nothing in a panel -- which is indistinguishable, from the
    user's side, from a widget that cannot be added at all. It throws no error,
    so nothing else catches it. These tests exist because it happened.
    """

    def setUp(self):
        qml = MAIN_QML.read_text()
        start = qml.index("compactRepresentation:")
        self.compact = qml[start:qml.index("fullRepresentation:", start)]

    def test_both_axes_are_constrained_in_all_three_ways(self):
        for prop in ("minimumWidth", "maximumWidth", "preferredWidth",
                     "minimumHeight", "maximumHeight", "preferredHeight"):
            with self.subTest(prop=prop):
                self.assertIn(f"Layout.{prop}", self.compact,
                              f"compact representation never sets Layout.{prop}")

    def test_it_branches_on_form_factor(self):
        """Horizontal and vertical panels need opposite axes pinned."""
        self.assertIn("PlasmaCore.Types.Vertical", self.compact)
        for prop in ("Layout.minimumWidth", "Layout.maximumWidth",
                     "Layout.minimumHeight", "Layout.maximumHeight"):
            with self.subTest(prop=prop):
                line = next(l for l in self.compact.splitlines()
                            if l.strip().startswith(prop))
                self.assertIn("vertical", line,
                              f"{prop} does not depend on the form factor")

    def test_no_axis_is_pinned_to_zero(self):
        """The original bug: `vertical ? 0 : ...` on the cross axis."""
        for line in self.compact.splitlines():
            if line.strip().startswith("Layout."):
                with self.subTest(line=line.strip()):
                    self.assertNotRegex(line, r"[?:]\s*0\s*$",
                                        "a Layout constraint resolves to zero")


class TestRendererReadsOnlyEvaluatorFields(unittest.TestCase):
    """The renderer must not invent fields. See this module's docstring."""

    def setUp(self):
        self.qml = MAIN_QML.read_text()
        self.model = model()

    def test_every_session_field_the_qml_reads_is_emitted(self):
        session_keys = set(self.model["sessions"][0])
        used = set(re.findall(r"modelData\.(\w+)", self.qml))
        self.assertEqual(set(), used - session_keys,
                         f"QML reads session fields the evaluator does not emit: "
                         f"{sorted(used - session_keys)}")

    def test_every_overflow_field_the_qml_reads_is_emitted(self):
        overflow_keys = set(self.model["overflow"])
        used = set(re.findall(r"root\.overflow\.(\w+)", self.qml))
        self.assertEqual(set(), used - overflow_keys,
                         f"QML reads overflow fields the evaluator does not emit: "
                         f"{sorted(used - overflow_keys)}")

    def test_every_top_level_field_the_qml_reads_is_emitted(self):
        top_keys = set(self.model)
        used = set(re.findall(r"root\.model\.(\w+)", self.qml))
        used |= set(re.findall(r"\bparsed\.(\w+)", self.qml))
        self.assertEqual(set(), used - top_keys,
                         f"QML reads model fields the evaluator does not emit: "
                         f"{sorted(used - top_keys)}")

    def test_the_qml_passes_the_slot_count_through_rather_than_slicing(self):
        """Slot allocation is the evaluator's job. If the QML ever starts
        trimming the list itself, the popup and `doctor` diverge."""
        self.assertIn("--slots", self.qml)

    def test_every_colour_name_the_evaluator_emits_is_handled(self):
        """A colour name with no case in colourFor() falls through to the
        disabled/grey default, which would silently mis-render a state."""
        handled = set(re.findall(r'case "(\w+)":', self.qml))
        self.assertEqual(set(), set(evaluator.COLOUR.values()) - handled,
                         "colourFor() has no case for every evaluator colour")


if __name__ == "__main__":
    unittest.main()
