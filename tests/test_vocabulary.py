"""State vocabulary integrity.

These run from Phase 0 onward, before any renderer exists, in the same spirit as
the fixture tests: a vocabulary that contradicts itself shows up as a failing
test rather than as a glyph nobody can tell apart six months later.

Nothing here touches a renderer. It checks that the tables in
docs/state-vocabulary.md are complete, mutually consistent, and consistent with
the state set the spec already fixed.
"""

import unicodedata
import unittest

import support


class TestRolesCoverEveryState(unittest.TestCase):
    def test_every_state_has_a_role(self):
        self.assertEqual(sorted(support.STATE_ROLES), sorted(support.PRIORITY))

    def test_no_role_is_used_twice(self):
        roles = list(support.STATE_ROLES.values())
        self.assertEqual(len(roles), len(set(roles)))

    def test_every_role_is_one_kirigami_actually_exposes(self):
        # Finding H. Inventing a role name yields a null colour at runtime.
        for state, role in support.STATE_ROLES.items():
            with self.subTest(state=state):
                self.assertIn(role, support.KIRIGAMI_TEXT_ROLES)

    def test_reserved_roles_are_not_claimed_by_a_state(self):
        for role in support.RESERVED_ROLES:
            self.assertNotIn(role, support.STATE_ROLES.values())

    def test_reserved_roles_are_real_roles(self):
        self.assertTrue(support.RESERVED_ROLES <= support.KIRIGAMI_TEXT_ROLES)

    def test_the_theme_has_room_to_spare(self):
        # If this ever fails, a new state has exhausted the palette and the one
        # role per state rule needs revisiting rather than quietly bending.
        self.assertLessEqual(len(support.STATE_ROLES), len(support.KIRIGAMI_TEXT_ROLES))

    def test_stale_is_not_a_role(self):
        # stale is the bottom of the intensity ramp, not a colour, so a stale
        # session keeps its own state colour.
        self.assertNotIn("stale", support.STATE_ROLES)


class TestGlyphsAreDistinguishable(unittest.TestCase):
    def test_every_state_has_a_glyph(self):
        self.assertEqual(sorted(support.STATE_GLYPHS), sorted(support.PRIORITY))

    def test_state_glyphs_are_distinct(self):
        glyphs = list(support.STATE_GLYPHS.values())
        self.assertEqual(len(glyphs), len(set(glyphs)))

    def test_tool_class_glyphs_are_distinct(self):
        glyphs = list(support.TOOL_CLASS_GLYPHS.values())
        self.assertEqual(len(glyphs), len(set(glyphs)))

    def test_error_kind_glyphs_are_distinct(self):
        glyphs = list(support.ERROR_KIND_GLYPHS.values())
        self.assertEqual(len(glyphs), len(set(glyphs)))

    def test_no_subtype_glyph_collides_with_another_state(self):
        # A tool glyph that equals the thinking glyph would make the two states
        # indistinguishable, which defeats the whole vocabulary.
        others = {state: glyph for state, glyph in support.STATE_GLYPHS.items()
                  if state not in ("tool", "error")}
        for family in (support.TOOL_CLASS_GLYPHS, support.ERROR_KIND_GLYPHS):
            for key, glyph in family.items():
                with self.subTest(key=key, glyph=glyph):
                    self.assertNotIn(glyph, others.values())

    def test_every_glyph_is_a_single_character(self):
        # The row reserves one fixed slot per session. A two-codepoint glyph
        # would not fit that assumption.
        families = (support.STATE_GLYPHS, support.TOOL_CLASS_GLYPHS,
                    support.ERROR_KIND_GLYPHS)
        for family in families:
            for key, glyph in family.items():
                with self.subTest(key=key):
                    self.assertEqual(len(glyph), 1)

    def test_no_glyph_carries_a_variation_selector(self):
        # A trailing U+FE0F forces emoji presentation, which paints its own
        # colour and would override the theme role.
        families = (support.STATE_GLYPHS, support.TOOL_CLASS_GLYPHS,
                    support.ERROR_KIND_GLYPHS)
        for family in families:
            for key, glyph in family.items():
                with self.subTest(key=key):
                    self.assertNotIn("️", glyph)

    def test_every_suspect_glyph_is_actually_in_use(self):
        # Open item 15. The suspect list is hand-declared, since the standard
        # library exposes no Emoji_Presentation property, so the risk is that it
        # rots into naming glyphs the vocabulary no longer uses.
        in_use = set()
        for family in (support.STATE_GLYPHS, support.TOOL_CLASS_GLYPHS,
                       support.ERROR_KIND_GLYPHS):
            in_use.update(family.values())
        for glyph in support.EMOJI_PRESENTATION_SUSPECT:
            with self.subTest(glyph=glyph):
                self.assertIn(glyph, in_use)

    def test_suspects_are_all_symbol_other(self):
        # Necessary, not sufficient: every emoji-presentation character is So,
        # but plenty of So characters render as text. This catches a plain
        # letter or digit being added to the list by mistake.
        for glyph in support.EMOJI_PRESENTATION_SUSPECT:
            with self.subTest(glyph=glyph):
                self.assertEqual(unicodedata.category(glyph), "So")

    def test_the_state_carrying_the_most_urgency_is_among_the_suspects(self):
        # If ⛔ turns out to be colour emoji, error is the state that loses its
        # theme role, which is the one worth knowing about first.
        self.assertIn(support.STATE_GLYPHS["error"], support.EMOJI_PRESENTATION_SUSPECT)


class TestToolClasses(unittest.TestCase):
    def test_every_class_has_a_glyph(self):
        self.assertEqual(sorted(support.TOOL_CLASSES), sorted(support.TOOL_CLASS_GLYPHS))

    def test_no_tool_is_claimed_by_two_classes(self):
        seen = set()
        for name, tools in support.TOOL_CLASSES.items():
            for tool in tools:
                with self.subTest(tool=tool):
                    self.assertNotIn(tool, seen)
                seen.add(tool)

    def test_other_is_the_empty_catch_all(self):
        # An unrecognised tool from a future Claude Code release must land here
        # rather than be mislabelled, so it must claim no tool names of its own.
        self.assertEqual(support.TOOL_CLASSES["other"], ())

    def test_the_tools_the_probe_actually_saw_are_classified(self):
        classified = {tool for tools in support.TOOL_CLASSES.values() for tool in tools}
        for tool in ("Bash", "Edit"):  # docs/hook-events.md, observed sequences
            with self.subTest(tool=tool):
                self.assertIn(tool, classified)


class TestErrorKinds(unittest.TestCase):
    def test_an_unregistered_kind_falls_back(self):
        # Finding C: the set of recognised kinds is fixed at install time, so an
        # unregistered failure yields error with a null error_kind.
        self.assertIn(None, support.ERROR_KIND_GLYPHS)

    def test_the_fallback_is_the_base_error_glyph(self):
        self.assertEqual(support.ERROR_KIND_GLYPHS[None], support.STATE_GLYPHS["error"])

    def test_wait_and_act_kinds_are_both_present(self):
        # The distinction the split exists to draw.
        self.assertIn("rate_limit", support.ERROR_KIND_GLYPHS)
        self.assertIn("billing_error", support.ERROR_KIND_GLYPHS)


class TestIntensity(unittest.TestCase):
    def test_attention_states_are_real_states(self):
        self.assertTrue(support.ATTENTION_STATES <= set(support.PRIORITY))

    def test_attention_states_are_the_top_of_the_priority_order(self):
        # They do not ramp, so they must be exactly the highest-priority block;
        # a gap would mean a ramping state outranks a non-ramping one.
        top = support.PRIORITY[:len(support.ATTENTION_STATES)]
        self.assertEqual(set(top), support.ATTENTION_STATES)

    def test_the_floor_leaves_a_stale_session_readable(self):
        self.assertGreater(support.INTENSITY_FLOOR, 0.0)
        self.assertLess(support.INTENSITY_FLOOR, 1.0)


class TestOrdinals(unittest.TestCase):
    def test_there_are_nine_before_the_overflow_marker(self):
        self.assertEqual(len(support.ORDINAL_GLYPHS), 9)

    def test_ordinals_are_distinct(self):
        self.assertEqual(len(set(support.ORDINAL_GLYPHS)), 9)

    def test_the_overflow_marker_is_not_one_of_them(self):
        self.assertNotIn(support.ORDINAL_OVERFLOW, support.ORDINAL_GLYPHS)

    def test_ordinals_do_not_collide_with_any_glyph(self):
        glyphs = set(support.STATE_GLYPHS.values())
        glyphs |= set(support.TOOL_CLASS_GLYPHS.values())
        glyphs |= set(support.ERROR_KIND_GLYPHS.values())
        for ordinal in support.ORDINAL_GLYPHS + support.ORDINAL_OVERFLOW:
            with self.subTest(ordinal=ordinal):
                self.assertNotIn(ordinal, glyphs)


class TestVocabularyMatchesTheDocument(unittest.TestCase):
    """The document is the explanation; these tables are the specification."""

    def setUp(self):
        self.text = (support.REPO_ROOT / "docs" / "state-vocabulary.md").read_text()

    def test_every_state_is_named_in_the_document(self):
        for state in support.PRIORITY:
            with self.subTest(state=state):
                self.assertIn(state, self.text)

    def test_every_role_is_named_in_the_document(self):
        for role in support.STATE_ROLES.values():
            with self.subTest(role=role):
                self.assertIn(role, self.text)

    def test_every_glyph_appears_in_the_document(self):
        for family in (support.STATE_GLYPHS, support.TOOL_CLASS_GLYPHS,
                       support.ERROR_KIND_GLYPHS):
            for key, glyph in family.items():
                with self.subTest(key=key):
                    self.assertIn(glyph, self.text)

    def test_the_document_carries_a_collapse_order(self):
        self.assertIn("Collapse order", self.text)


if __name__ == "__main__":
    unittest.main()
