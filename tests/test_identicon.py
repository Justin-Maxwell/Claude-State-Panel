"""Konsole identicon tool.

Everything here is headless: no Plasma shell, no Konsole, no session bus. The
D-Bus layer is exercised by asserting on the argument lists it would run, which
is also how the "argument list, never a composed shell string" invariant is
kept honest.
"""

import os
import pathlib
import struct
import subprocess
import tempfile
import unittest
import zlib

import support

ident = support.load_script(support.IDENTICON, "claude_state_identicon")

# Two unrelated real-world-shaped paths, used throughout.
KEY_A = "/home/justin/src/claude-state-panel"
KEY_B = "/home/justin/src/clautana"


class TestKeyNormalisation(unittest.TestCase):
    def test_trailing_separator_is_stripped(self):
        self.assertEqual(ident.normalise_key(KEY_A + "/"), ident.normalise_key(KEY_A))

    def test_relative_path_resolves_against_cwd(self):
        with tempfile.TemporaryDirectory() as tmp:
            here = os.getcwd()
            os.chdir(tmp)
            try:
                # macOS-style /private symlinks would break a literal compare.
                self.assertEqual(ident.normalise_key("."), os.path.abspath("."))
            finally:
                os.chdir(here)

    def test_root_survives_stripping(self):
        self.assertEqual(ident.normalise_key("/"), "/")

    def test_home_is_expanded(self):
        self.assertFalse(ident.normalise_key("~/x").startswith("~"))


class TestRemoteUrlNormalisation(unittest.TestCase):
    """Every way of naming one repository must collapse to one key."""

    EQUIVALENT = [
        "https://github.com/Owner/Repo.git",
        "https://github.com/Owner/Repo",
        "https://github.com/owner/repo/",
        "https://token@github.com/Owner/Repo.git",
        "https://user:pass@github.com/Owner/Repo.git",
        "git@github.com:Owner/Repo.git",
        "git@github.com:Owner/Repo",
        "ssh://git@github.com/Owner/Repo.git",
        "ssh://git@github.com:2222/Owner/Repo.git",
        "git://github.com/Owner/Repo.git",
    ]

    def test_all_spellings_agree(self):
        for url in self.EQUIVALENT:
            with self.subTest(url=url):
                self.assertEqual(
                    ident.normalise_remote_url(url), "github.com/owner/repo"
                )

    def test_the_host_is_kept_so_forges_stay_distinct(self):
        self.assertNotEqual(
            ident.normalise_remote_url("https://github.com/a/b"),
            ident.normalise_remote_url("https://gitlab.com/a/b"),
        )

    def test_nested_groups_survive(self):
        self.assertEqual(
            ident.normalise_remote_url("https://gitlab.com/Group/Sub/Repo.git"),
            "gitlab.com/group/sub/repo",
        )

    def test_a_repo_named_git_is_not_truncated(self):
        self.assertEqual(
            ident.normalise_remote_url("https://github.com/owner/git.git"),
            "github.com/owner/git",
        )

    def test_local_remotes_are_refused(self):
        # No more portable than the working directory, so no special treatment.
        for url in ("/srv/git/repo.git", "file:///srv/git/repo.git", "", None):
            with self.subTest(url=url):
                self.assertIsNone(ident.normalise_remote_url(url))

    def test_a_url_with_no_path_is_refused(self):
        self.assertIsNone(ident.normalise_remote_url("https://github.com"))


class TestKeyResolution(unittest.TestCase):
    """Built on real repositories, because the whole point is git's behaviour."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null",
                        GIT_CONFIG_SYSTEM="/dev/null")

    def _git(self, *args, cwd):
        subprocess.run(["git", "-C", str(cwd), *args], check=True,
                       capture_output=True, text=True, env=self.env)

    def _repo(self, name, remote=None):
        path = self.root / name
        path.mkdir(parents=True)
        self._git("init", "-q", "-b", "main", cwd=path)
        self._git("config", "user.email", "t@example.invalid", cwd=path)
        self._git("config", "user.name", "Test", cwd=path)
        (path / "README").write_text("x\n")
        self._git("add", "-A", cwd=path)
        self._git("commit", "-qm", "init", cwd=path)
        if remote:
            self._git("remote", "add", "origin", remote, cwd=path)
        return path

    def test_a_repo_with_a_remote_keys_on_the_remote(self):
        path = self._repo("proj", "git@github.com:Owner/Repo.git")
        self.assertEqual(ident.resolve_key(path), ("github.com/owner/repo", "remote"))

    def test_a_subdirectory_gets_the_same_key_as_the_root(self):
        path = self._repo("proj", "https://github.com/Owner/Repo.git")
        (path / "docs").mkdir()
        self.assertEqual(ident.resolve_key(path / "docs"), ident.resolve_key(path))

    def test_a_worktree_gets_the_same_key_as_the_main_checkout(self):
        # This is the case that decides it. The desktop app puts each parallel
        # session in its own worktree, so a path-derived key would give every
        # session in one project a different identicon.
        path = self._repo("proj", "https://github.com/Owner/Repo.git")
        tree = self.root / "wt"
        # Detached, because git refuses to check out a branch that another
        # worktree already holds.
        self._git("worktree", "add", "-q", "--detach", str(tree), cwd=path)
        self.assertNotEqual(ident.repo_toplevel(tree), ident.repo_toplevel(path))
        self.assertEqual(ident.resolve_key(tree), ident.resolve_key(path))

    def test_two_clones_at_different_paths_agree(self):
        one = self._repo("clone-a", "https://github.com/Owner/Repo.git")
        two = self._repo("clone-b", "git@github.com:Owner/Repo.git")
        self.assertEqual(ident.resolve_key(one)[0], ident.resolve_key(two)[0])

    def test_a_repo_with_no_remote_falls_back_to_its_root(self):
        path = self._repo("local-only")
        key, source = ident.resolve_key(path)
        self.assertEqual(source, "toplevel")
        self.assertEqual(key, ident.normalise_key(path))

    def test_a_non_repository_falls_back_to_the_path(self):
        plain = self.root / "plain"
        plain.mkdir()
        key, source = ident.resolve_key(plain)
        self.assertEqual(source, "path")
        self.assertEqual(key, ident.normalise_key(plain))

    def test_a_committed_override_beats_the_remote(self):
        path = self._repo("proj", "https://github.com/Owner/Repo.git")
        (path / ident.OVERRIDE_FILENAME).write_text("my-chosen-seed\n")
        self.assertEqual(ident.resolve_key(path), ("my-chosen-seed", "override"))

    def test_an_override_at_the_root_applies_in_a_subdirectory(self):
        path = self._repo("proj", "https://github.com/Owner/Repo.git")
        (path / ident.OVERRIDE_FILENAME).write_text("my-chosen-seed\n")
        (path / "docs").mkdir()
        self.assertEqual(ident.resolve_key(path / "docs")[0], "my-chosen-seed")

    def test_an_override_ignores_comments_and_blank_lines(self):
        path = self._repo("proj", "https://github.com/Owner/Repo.git")
        (path / ident.OVERRIDE_FILENAME).write_text("# why\n\n  seed  \n")
        self.assertEqual(ident.resolve_key(path)[0], "seed")

    def test_an_empty_override_is_ignored_rather_than_obeyed(self):
        path = self._repo("proj", "https://github.com/Owner/Repo.git")
        (path / ident.OVERRIDE_FILENAME).write_text("# only a comment\n")
        self.assertEqual(ident.resolve_key(path)[1], "remote")

    def test_an_explicit_key_beats_everything(self):
        path = self._repo("proj", "https://github.com/Owner/Repo.git")
        (path / ident.OVERRIDE_FILENAME).write_text("committed\n")
        self.assertEqual(ident.resolve_key(path, explicit="cli"), ("cli", "explicit"))

    def test_every_source_has_a_note_for_the_show_command(self):
        self.assertEqual(
            sorted(ident.SOURCE_NOTES),
            ["explicit", "override", "path", "remote", "toplevel"],
        )


class TestGrid(unittest.TestCase):
    def test_grid_is_five_by_five_booleans(self):
        grid = ident.identicon_grid(KEY_A)
        self.assertEqual(len(grid), 5)
        for row in grid:
            self.assertEqual(len(row), 5)
            for cell in row:
                self.assertIsInstance(cell, bool)

    def test_grid_is_mirrored_about_the_centre_column(self):
        for key in (KEY_A, KEY_B, "/", "/tmp/x"):
            with self.subTest(key=key):
                for row in ident.identicon_grid(key):
                    self.assertEqual(row[0], row[4])
                    self.assertEqual(row[1], row[3])

    def test_grid_is_deterministic(self):
        self.assertEqual(ident.identicon_grid(KEY_A), ident.identicon_grid(KEY_A))

    def test_different_paths_differ(self):
        # Not a guarantee for every pair, but these two must not collide.
        self.assertNotEqual(ident.identicon_grid(KEY_A), ident.identicon_grid(KEY_B))

    def test_at_least_one_cell_is_set_across_a_sample(self):
        blank = 0
        for n in range(200):
            if not any(any(row) for row in ident.identicon_grid(f"/p/{n}")):
                blank += 1
        self.assertEqual(blank, 0)


class TestColour(unittest.TestCase):
    def test_components_are_bytes(self):
        for component in ident.identicon_colour(KEY_A):
            self.assertGreaterEqual(component, 0)
            self.assertLessEqual(component, 255)

    def test_colour_is_deterministic(self):
        self.assertEqual(ident.identicon_colour(KEY_A), ident.identicon_colour(KEY_A))

    def test_hex_colour_round_trips(self):
        rgb = ident.identicon_colour(KEY_A)
        text = ident.hex_colour(rgb)
        self.assertRegex(text, r"^#[0-9a-f]{6}$")
        self.assertEqual(tuple(int(text[i:i + 2], 16) for i in (1, 3, 5)), rgb)

    def test_lightness_zero_is_black_whatever_the_path(self):
        self.assertEqual(ident.identicon_colour(KEY_A, lightness=0.0), (0, 0, 0))


class TestDerivedNames(unittest.TestCase):
    def test_icon_name_is_prefixed_and_stable(self):
        name = ident.icon_name(KEY_A)
        self.assertTrue(name.startswith(ident.ICON_PREFIX + "-"))
        self.assertEqual(name, ident.icon_name(KEY_A))
        self.assertNotEqual(name, ident.icon_name(KEY_B))

    def test_icon_name_is_a_safe_theme_name(self):
        self.assertRegex(ident.icon_name("/home/j/Some Project (v2)"), r"^[a-z0-9-]+$")

    def test_profile_name_carries_the_project_and_a_discriminator(self):
        name = ident.profile_name(KEY_A)
        self.assertTrue(name.startswith("claude-state-panel ["))
        self.assertTrue(name.endswith("]"))

    def test_same_basename_different_path_gets_a_distinct_profile_name(self):
        self.assertNotEqual(
            ident.profile_name("/home/a/work"), ident.profile_name("/home/b/work")
        )

    def test_badge_label_uses_initials_when_the_name_has_separators(self):
        self.assertEqual(ident.badge_label("/x/claude-state-panel"), "CS")
        self.assertEqual(ident.badge_label("/x/my_project"), "MP")
        self.assertEqual(ident.badge_label("/x/dot.name"), "DN")

    def test_badge_label_falls_back_to_leading_characters(self):
        self.assertEqual(ident.badge_label("/x/clautana"), "CL")

    def test_badge_label_is_never_longer_than_two_characters(self):
        for path in ("/x/a-b-c-d-e", "/x/clautana", "/x/z", "/"):
            with self.subTest(path=path):
                self.assertLessEqual(len(ident.badge_label(path)), 2)


class TestProfileBody(unittest.TestCase):
    def setUp(self):
        self.body = ident.profile_body(KEY_A)

    def test_icon_lives_under_general(self):
        # Profile.cpp: {Icon, "Icon", GENERAL_GROUP}.
        self.assertTrue(self.body.startswith("[General]\n"))
        self.assertIn(f"\nIcon={ident.icon_name(KEY_A)}\n", self.body)

    def test_name_matches_what_set_profile_will_be_asked_for(self):
        self.assertIn(f"\nName={ident.profile_name(KEY_A)}\n", self.body)

    def test_parent_is_declared_so_nothing_else_changes(self):
        self.assertIn("\nParent=FALLBACK/\n", self.body)

    def test_no_other_keys_are_set(self):
        keys = [line.split("=", 1)[0] for line in self.body.splitlines() if "=" in line]
        self.assertEqual(sorted(keys), ["Icon", "Name", "Parent"])

    def test_filename_is_prefixed_for_clean_uninstall(self):
        self.assertTrue(ident.profile_filename(KEY_A).startswith(ident.ICON_PREFIX + "-"))
        self.assertTrue(ident.profile_filename(KEY_A).endswith(".profile"))


class TestPngEncoding(unittest.TestCase):
    def setUp(self):
        self.size = 32
        self.data = ident.render_png(KEY_A, self.size)

    def test_signature(self):
        self.assertEqual(self.data[:8], b"\x89PNG\r\n\x1a\n")

    def test_ihdr_declares_the_requested_geometry_and_rgba(self):
        width, height, depth, colour_type = struct.unpack(">IIBB", self.data[16:26])
        self.assertEqual((width, height), (self.size, self.size))
        self.assertEqual(depth, 8)
        self.assertEqual(colour_type, 6)

    def test_chunk_crcs_are_correct(self):
        offset = 8
        seen = []
        while offset < len(self.data):
            length = struct.unpack(">I", self.data[offset:offset + 4])[0]
            tag = self.data[offset + 4:offset + 8]
            body = self.data[offset + 8:offset + 8 + length]
            crc = struct.unpack(">I", self.data[offset + 8 + length:offset + 12 + length])[0]
            self.assertEqual(crc, zlib.crc32(tag + body) & 0xFFFFFFFF, tag)
            seen.append(tag)
            offset += 12 + length
        self.assertEqual(seen, [b"IHDR", b"IDAT", b"IEND"])

    def test_pixels_round_trip_to_the_declared_size(self):
        rgba = ident.render_rgba(KEY_A, self.size)
        self.assertEqual(len(rgba), self.size * self.size * 4)

    def test_background_is_transparent_by_default(self):
        rgba = ident.render_rgba(KEY_A, self.size)
        self.assertEqual(rgba[3], 0)  # top-left alpha, always outside the grid

    def test_an_opaque_background_fills_every_pixel(self):
        rgba = ident.render_rgba(KEY_A, self.size, background=(255, 255, 255))
        self.assertEqual(set(rgba[3::4]), {255})

    def test_a_filled_cell_carries_the_derived_colour(self):
        size = 55  # cell 10, margin 2, so cell centres are easy to hit
        grid = ident.identicon_grid(KEY_A)
        colour = ident.identicon_colour(KEY_A)
        rgba = ident.render_rgba(KEY_A, size)
        cell, margin = ident._geometry(size)
        for row in range(5):
            for column in range(5):
                x = margin + column * cell + cell // 2
                y = margin + row * cell + cell // 2
                offset = (y * size + x) * 4
                pixel = tuple(rgba[offset:offset + 3])
                alpha = rgba[offset + 3]
                with self.subTest(row=row, column=column):
                    if grid[row][column]:
                        self.assertEqual(pixel, colour)
                        self.assertEqual(alpha, 255)
                    else:
                        self.assertEqual(alpha, 0)

    def test_every_install_size_renders(self):
        for size in ident.INSTALL_SIZES:
            with self.subTest(size=size):
                data = ident.render_png(KEY_A, size)
                width, height = struct.unpack(">II", data[16:24])
                self.assertEqual((width, height), (size, size))

    def test_the_grid_always_fits_the_canvas(self):
        for size in ident.INSTALL_SIZES:
            cell, margin = ident._geometry(size)
            with self.subTest(size=size):
                self.assertGreaterEqual(margin, 0)
                self.assertLessEqual(margin * 2 + cell * 5, size)


class TestSvg(unittest.TestCase):
    def test_one_rect_per_filled_cell(self):
        svg = ident.render_svg(KEY_A, 100)
        filled = sum(sum(1 for cell in row if cell) for row in ident.identicon_grid(KEY_A))
        self.assertEqual(svg.count("<rect"), filled)

    def test_background_adds_exactly_one_more_rect(self):
        plain = ident.render_svg(KEY_A, 100).count("<rect")
        filled = ident.render_svg(KEY_A, 100, background=(0, 0, 0)).count("<rect")
        self.assertEqual(filled, plain + 1)

    def test_it_is_a_closed_svg_element(self):
        svg = ident.render_svg(KEY_A, 100)
        self.assertTrue(svg.startswith("<svg "))
        self.assertTrue(svg.rstrip().endswith("</svg>"))


class TestInstallation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_install_writes_one_png_per_size_plus_a_scalable_svg(self):
        written = ident.install_icon(KEY_A, root=self.root)
        self.assertEqual(len(written), len(ident.INSTALL_SIZES) + 1)
        for size in ident.INSTALL_SIZES:
            target = self.root / f"{size}x{size}" / "apps" / f"{ident.icon_name(KEY_A)}.png"
            with self.subTest(size=size):
                self.assertTrue(target.is_file())
        self.assertTrue(
            (self.root / "scalable" / "apps" / f"{ident.icon_name(KEY_A)}.svg").is_file()
        )

    def test_install_is_idempotent(self):
        first = ident.install_icon(KEY_A, root=self.root)
        second = ident.install_icon(KEY_A, root=self.root)
        self.assertEqual(first, second)
        self.assertEqual(len(ident.installed_icons(root=self.root)), 1)

    def test_listing_finds_only_our_own_icons(self):
        ident.install_icon(KEY_A, root=self.root)
        stray = self.root / "48x48" / "apps" / "firefox.png"
        stray.parent.mkdir(parents=True, exist_ok=True)
        stray.write_bytes(b"")
        found = ident.installed_icons(root=self.root)
        self.assertEqual(list(found), [ident.icon_name(KEY_A)])

    def test_removal_takes_every_size_and_leaves_the_rest(self):
        ident.install_icon(KEY_A, root=self.root)
        ident.install_icon(KEY_B, root=self.root)
        removed = ident.remove_icon(ident.icon_name(KEY_A), root=self.root)
        self.assertEqual(len(removed), len(ident.INSTALL_SIZES) + 1)
        self.assertEqual(list(ident.installed_icons(root=self.root)), [ident.icon_name(KEY_B)])

    def test_listing_an_absent_root_is_empty_not_an_error(self):
        self.assertEqual(ident.installed_icons(root=self.root / "nope"), {})

    def test_profile_is_written_where_konsole_looks(self):
        target = ident.install_profile(KEY_A, directory=self.root)
        self.assertEqual(target.name, ident.profile_filename(KEY_A))
        self.assertEqual(target.read_text(), ident.profile_body(KEY_A))
        self.assertEqual(ident.installed_profiles(directory=self.root), [target])


class TestSessionResolution(unittest.TestCase):
    def setUp(self):
        for variable in ("KONSOLE_DBUS_SERVICE", "KONSOLE_DBUS_SESSION"):
            self.addCleanup(os.environ.pop, variable, None)
            os.environ.pop(variable, None)

    def test_environment_is_used_when_running_inside_konsole(self):
        os.environ["KONSOLE_DBUS_SERVICE"] = "org.kde.konsole-1234"
        os.environ["KONSOLE_DBUS_SESSION"] = "/Sessions/2"
        self.assertEqual(
            ident.resolve_session(), ("org.kde.konsole-1234", "/Sessions/2")
        )

    def test_an_explicit_spec_overrides_the_environment(self):
        os.environ["KONSOLE_DBUS_SERVICE"] = "org.kde.konsole-1234"
        os.environ["KONSOLE_DBUS_SESSION"] = "/Sessions/2"
        self.assertEqual(
            ident.resolve_session("org.kde.konsole-9:/Sessions/7"),
            ("org.kde.konsole-9", "/Sessions/7"),
        )

    def test_a_malformed_spec_is_rejected(self):
        with self.assertRaises(ident.DBusError):
            ident.resolve_session("org.kde.konsole-9")


class TestDBusInvocation(unittest.TestCase):
    """The calls are never composed into a shell string. Spec invariant."""

    def setUp(self):
        self.calls = []
        original = ident._run
        ident._run = self._record
        self.addCleanup(setattr, ident, "_run", original)

    def _record(self, argv):
        self.calls.append(argv)
        return ""

    def test_qdbus_call_is_an_argument_list(self):
        ident.dbus_call("org.kde.konsole-1", "/Sessions/1", "setBadgeText",
                        ["CS"], qdbus="/usr/bin/qdbus6")
        self.assertEqual(len(self.calls), 1)
        argv = self.calls[0]
        self.assertIsInstance(argv, list)
        for item in argv:
            self.assertIsInstance(item, str)
        self.assertEqual(argv[0], "/usr/bin/qdbus6")
        self.assertIn("org.kde.konsole.Session.setBadgeText", argv)
        self.assertIn("CS", argv)

    def test_a_label_with_spaces_stays_one_argument(self):
        ident.dbus_call("org.kde.konsole-1", "/Sessions/1", "setBadgeText",
                        ["a b; rm -rf /"], qdbus="/usr/bin/qdbus6")
        self.assertIn("a b; rm -rf /", self.calls[0])

    def test_non_string_arguments_are_stringified(self):
        ident.dbus_call("org.kde.konsole-1", "/Sessions/1", "setBadgeFontSize",
                        [12], qdbus="/usr/bin/qdbus6")
        self.assertIn("12", self.calls[0])


class TestCliSurface(unittest.TestCase):
    def test_every_subcommand_parses_with_no_further_arguments(self):
        parser = ident.build_parser()
        for command in ("show", "render", "install", "list", "uninstall",
                        "sessions", "probe", "badge", "profile", "demo", "doctor"):
            with self.subTest(command=command):
                args = parser.parse_args([command])
                self.assertTrue(callable(args.func))

    def test_commands_that_touch_a_session_accept_one(self):
        parser = ident.build_parser()
        for command in ("probe", "badge", "profile", "demo"):
            with self.subTest(command=command):
                args = parser.parse_args([command, "--session", "org.kde.konsole-1:/Sessions/1"])
                self.assertEqual(args.session, "org.kde.konsole-1:/Sessions/1")

    def test_the_tool_is_executable(self):
        self.assertTrue(os.access(support.IDENTICON, os.X_OK))


if __name__ == "__main__":
    unittest.main()
