#!/usr/bin/env python3
"""Per-project identicons for Konsole tabs.

A testbed for the two compile-free routes to a per-tab project marker, both
reached over Konsole's session D-Bus interface:

  badge    org.kde.konsole.Session exposes setBadgeText, setBadgeColor and
           friends as Q_SCRIPTABLE. Paints over the terminal view.
  profile  setProfile is Q_SCRIPTABLE while setIconName is not, so the tab-bar
           icon is reachable only by generating a profile that carries Icon=.

The third route, an identicon on the session toolbar itself, needs a C++
IKonsolePlugin. Konsole installs no plugin headers, so that one cannot be built
out of tree at all. See docs/konsole-identicons.md.

Standard library only. Every subprocess is invoked with an argument list.
"""

import argparse
import colorsys
import hashlib
import os
import pathlib
import shutil
import struct
import subprocess
import sys
import zlib

# ---------------------------------------------------------------------------
# Identicon derivation
#
# GitHub-style: a 5x5 grid, left three columns drawn from the digest and
# mirrored onto the right two, so every identicon is vertically symmetric.
# The rule below is ours and is pinned by the test suite; it is not claimed to
# reproduce GitHub's output byte for byte.
# ---------------------------------------------------------------------------

GRID = 5
ICON_PREFIX = "claude-state-identicon"
INSTALL_SIZES = (16, 22, 24, 32, 48, 64, 128, 256)


def normalise_key(path):
    """Reduce a project path to the string everything else is derived from.

    Expanded, made absolute, and stripped of any trailing separator, so that
    `~/src/foo`, `~/src/foo/` and a relative path to the same place all yield
    one identicon.
    """
    expanded = os.path.expanduser(str(path))
    absolute = os.path.abspath(expanded)
    return absolute.rstrip(os.sep) or os.sep


def _digest(key):
    return hashlib.md5(key.encode("utf-8")).digest()


def identicon_grid(key):
    """Return the 5x5 grid as a list of rows of bools."""
    digest = _digest(key)
    grid = [[False] * GRID for _ in range(GRID)]
    for column in range(3):
        for row in range(GRID):
            if digest[column * GRID + row] % 2 == 0:
                grid[row][column] = True
                grid[row][GRID - 1 - column] = True
    return grid


def identicon_colour(key, saturation=0.55, lightness=0.50):
    """Return the foreground colour as an (r, g, b) triple of 0-255 ints.

    Hue comes from the one digest byte the grid does not consume, so the colour
    and the pattern cannot drift apart.
    """
    hue = _digest(key)[15] * 360 // 256
    red, green, blue = colorsys.hls_to_rgb(hue / 360.0, lightness, saturation)
    return (round(red * 255), round(green * 255), round(blue * 255))


def hex_colour(rgb):
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def short_hash(key, length=12):
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:length]


def icon_name(key):
    """Theme icon name. Konsole's profile Icon= is a theme name, not a path."""
    return f"{ICON_PREFIX}-{short_hash(key)}"


def project_name(key):
    return os.path.basename(key) or key


def badge_label(key, limit=2):
    """A one or two character label for the badge overlay.

    Initials where the project name has separators, otherwise the leading
    characters. Upper-cased, because the badge is small.
    """
    name = project_name(key)
    words = [part for part in name.replace("_", "-").replace(".", "-").replace(" ", "-").split("-") if part]
    if len(words) >= 2:
        return "".join(word[0] for word in words[:limit]).upper()
    return name[:limit].upper()


def profile_name(key):
    """Display name of the generated profile, and what setProfile matches on."""
    return f"{project_name(key)} [{short_hash(key, 6)}]"


def profile_filename(key):
    return f"{ICON_PREFIX}-{short_hash(key)}.profile"


def profile_body(key, parent="FALLBACK/"):
    """The .profile file contents.

    Icon lives under [General], per Profile.cpp: {Icon, "Icon", GENERAL_GROUP}.
    Nothing else is set, so the profile inherits everything from its parent and
    the switch changes the icon alone.
    """
    return (
        "[General]\n"
        f"Name={profile_name(key)}\n"
        f"Parent={parent}\n"
        f"Icon={icon_name(key)}\n"
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _geometry(size):
    """Cell size and margin for a square canvas.

    Cells are deliberately generous relative to the canvas so a 16px icon still
    reads as a pattern rather than a smudge.
    """
    cell = max(1, round(size / 5.5))
    if cell * GRID > size:
        cell = max(1, size // GRID)
    margin = (size - cell * GRID) // 2
    return cell, margin


def render_rgba(key, size, saturation=0.55, lightness=0.50, background=None):
    """Return raw RGBA bytes for a square identicon of the given size."""
    grid = identicon_grid(key)
    red, green, blue = identicon_colour(key, saturation, lightness)
    cell, margin = _geometry(size)

    if background is None:
        back = bytes((0, 0, 0, 0))
    else:
        back = bytes(tuple(background) + (255,))
    fore = bytes((red, green, blue, 255))

    rows = []
    for y in range(size):
        row = bytearray()
        grid_y = (y - margin) // cell if cell else -1
        inside_y = margin <= y < margin + cell * GRID
        for x in range(size):
            grid_x = (x - margin) // cell if cell else -1
            inside_x = margin <= x < margin + cell * GRID
            if inside_x and inside_y and grid[grid_y][grid_x]:
                row += fore
            else:
                row += back
        rows.append(bytes(row))
    return b"".join(rows)


def _png_chunk(tag, data):
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def encode_png(rgba, width, height):
    """Minimal 8-bit RGBA PNG encoder. Flat colour blocks compress to nothing."""
    stride = width * 4
    raw = b"".join(b"\x00" + rgba[y * stride:(y + 1) * stride] for y in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(raw, 9))
        + _png_chunk(b"IEND", b"")
    )


def render_png(key, size, **kwargs):
    return encode_png(render_rgba(key, size, **kwargs), size, size)


def render_svg(key, size=256, saturation=0.55, lightness=0.50, background=None):
    grid = identicon_grid(key)
    colour = hex_colour(identicon_colour(key, saturation, lightness))
    cell, margin = _geometry(size)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 {size} {size}">'
    ]
    if background is not None:
        parts.append(f'<rect width="{size}" height="{size}" fill="{hex_colour(background)}"/>')
    for row in range(GRID):
        for column in range(GRID):
            if grid[row][column]:
                x = margin + column * cell
                y = margin + row * cell
                parts.append(
                    f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" fill="{colour}"/>'
                )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def render_ansi(key):
    """Terminal preview, two spaces per cell on a background colour."""
    grid = identicon_grid(key)
    red, green, blue = identicon_colour(key)
    lines = []
    for row in grid:
        line = ""
        for filled in row:
            line += f"\033[48;2;{red};{green};{blue}m  \033[0m" if filled else "  "
        lines.append(line)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Icon theme installation
# ---------------------------------------------------------------------------


def icon_theme_root():
    data_home = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return pathlib.Path(data_home) / "icons" / "hicolor"


def konsole_profile_dir():
    data_home = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return pathlib.Path(data_home) / "konsole"


def install_icon(key, root=None, sizes=INSTALL_SIZES, **render_kwargs):
    """Write one PNG per size into the user's hicolor tree. Returns the paths.

    hicolor under XDG_DATA_HOME merges with the system theme, so no index.theme
    of our own is needed for QIcon::fromTheme to find these.
    """
    root = pathlib.Path(root) if root else icon_theme_root()
    name = icon_name(key)
    written = []
    for size in sizes:
        directory = root / f"{size}x{size}" / "apps"
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{name}.png"
        target.write_bytes(render_png(key, size, **render_kwargs))
        written.append(target)

    scalable = root / "scalable" / "apps"
    scalable.mkdir(parents=True, exist_ok=True)
    target = scalable / f"{name}.svg"
    target.write_text(render_svg(key, 256, **render_kwargs))
    written.append(target)
    return written


def installed_icons(root=None):
    """Every identicon this tool has installed, as {icon name: [paths]}."""
    root = pathlib.Path(root) if root else icon_theme_root()
    found = {}
    if not root.is_dir():
        return found
    for path in sorted(root.glob(f"*/apps/{ICON_PREFIX}-*")):
        found.setdefault(path.stem, []).append(path)
    return found


def remove_icon(name, root=None):
    root = pathlib.Path(root) if root else icon_theme_root()
    removed = []
    for path in sorted(root.glob(f"*/apps/{name}.*")):
        path.unlink()
        removed.append(path)
    return removed


def install_profile(key, directory=None, parent="FALLBACK/"):
    directory = pathlib.Path(directory) if directory else konsole_profile_dir()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / profile_filename(key)
    target.write_text(profile_body(key, parent))
    return target


def installed_profiles(directory=None):
    directory = pathlib.Path(directory) if directory else konsole_profile_dir()
    if not directory.is_dir():
        return []
    return sorted(directory.glob(f"{ICON_PREFIX}-*.profile"))


# ---------------------------------------------------------------------------
# D-Bus
# ---------------------------------------------------------------------------

SESSION_IFACE = "org.kde.konsole.Session"
QDBUS_CANDIDATES = ("qdbus6", "qdbus-qt6", "qdbus")


class DBusError(RuntimeError):
    pass


def find_qdbus():
    for candidate in QDBUS_CANDIDATES:
        found = shutil.which(candidate)
        if found:
            return found
    return None


def find_gdbus():
    return shutil.which("gdbus")


def _run(argv):
    completed = subprocess.run(argv, capture_output=True, text=True)
    if completed.returncode != 0:
        raise DBusError((completed.stderr or completed.stdout).strip() or f"{argv[0]} failed")
    return completed.stdout


def dbus_call(service, path, method, args=(), qdbus=None):
    """Call a method on a Konsole session. Argument list, never a shell string."""
    qdbus = qdbus or find_qdbus()
    if qdbus:
        return _run([qdbus, service, path, f"{SESSION_IFACE}.{method}", *[str(a) for a in args]])
    gdbus = find_gdbus()
    if not gdbus:
        raise DBusError("neither qdbus nor gdbus is on PATH")
    argv = [gdbus, "call", "--session", "--dest", service, "--object-path", path,
            "--method", f"{SESSION_IFACE}.{method}"]
    argv += [str(a) for a in args]
    return _run(argv)


def dbus_members(service, path):
    """Method names exposed on the object, for capability probing."""
    qdbus = find_qdbus()
    if qdbus:
        listing = _run([qdbus, service, path])
        names = set()
        for line in listing.splitlines():
            line = line.strip()
            if not line:
                continue
            head = line.split("(")[0].split()[-1]
            names.add(head.rsplit(".", 1)[-1])
        return names
    gdbus = find_gdbus()
    if not gdbus:
        raise DBusError("neither qdbus nor gdbus is on PATH")
    xml = _run([gdbus, "introspect", "--session", "--dest", service,
                "--object-path", path, "--xml"])
    names = set()
    for line in xml.splitlines():
        line = line.strip()
        if line.startswith("<method "):
            names.add(line.split('name="', 1)[1].split('"', 1)[0])
    return names


def list_konsole_services():
    qdbus = find_qdbus()
    if qdbus:
        return sorted(n for n in _run([qdbus]).split() if n.startswith("org.kde.konsole"))
    gdbus = find_gdbus()
    if not gdbus:
        return []
    out = _run([gdbus, "call", "--session", "--dest", "org.freedesktop.DBus",
                "--object-path", "/org/freedesktop/DBus",
                "--method", "org.freedesktop.DBus.ListNames"])
    return sorted({tok.strip("'\", []()") for tok in out.split(",")
                   if "org.kde.konsole" in tok})


def list_sessions(service):
    qdbus = find_qdbus()
    if not qdbus:
        return []
    return sorted(line.strip() for line in _run([qdbus, service]).splitlines()
                  if line.strip().startswith("/Sessions/"))


def resolve_session(spec=None):
    """Return (service, path) for the session to act on.

    With no spec, use the KONSOLE_DBUS_SERVICE and KONSOLE_DBUS_SESSION that
    Konsole exports into every session's environment, so running this inside
    the tab you want marked just works.
    """
    if spec:
        if ":" not in spec:
            raise DBusError(f"session spec must be service:/Sessions/N, got {spec!r}")
        service, path = spec.split(":", 1)
        return service, path

    service = os.environ.get("KONSOLE_DBUS_SERVICE")
    path = os.environ.get("KONSOLE_DBUS_SESSION")
    if service and path:
        return service, path

    services = list_konsole_services()
    if len(services) == 1:
        sessions = list_sessions(services[0])
        if len(sessions) == 1:
            return services[0], sessions[0]
    raise DBusError(
        "not running inside Konsole and could not pick a session unambiguously; "
        "pass --session service:/Sessions/N (see the `sessions` command)"
    )


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def _key_from_args(args):
    return normalise_key(args.path if args.path else os.getcwd())


def _render_kwargs(args):
    background = None
    if getattr(args, "background", None):
        text = args.background.lstrip("#")
        if len(text) != 6:
            raise SystemExit("--background wants a six digit hex colour")
        background = tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))
    return {
        "saturation": args.saturation,
        "lightness": args.lightness,
        "background": background,
    }


def cmd_show(args):
    key = _key_from_args(args)
    print(f"path      {key}")
    print(f"project   {project_name(key)}")
    print(f"icon      {icon_name(key)}")
    print(f"profile   {profile_name(key)}")
    print(f"badge     {badge_label(key)}")
    print(f"colour    {hex_colour(identicon_colour(key, args.saturation, args.lightness))}")
    print()
    print(render_ansi(key))
    return 0


def cmd_render(args):
    key = _key_from_args(args)
    kwargs = _render_kwargs(args)
    if args.format == "svg":
        data = render_svg(key, args.size, **kwargs).encode("utf-8")
    else:
        data = render_png(key, args.size, **kwargs)
    if args.out == "-":
        sys.stdout.buffer.write(data)
    else:
        pathlib.Path(args.out).write_bytes(data)
        print(f"wrote {args.out}")
    return 0


def cmd_install(args):
    key = _key_from_args(args)
    written = install_icon(key, **_render_kwargs(args))
    print(f"icon {icon_name(key)}")
    for path in written:
        print(f"  {path}")
    print()
    print("Konsole reads profile icons through QIcon::fromTheme, which caches. A")
    print("running Konsole may not show a brand new icon until it restarts.")
    return 0


def cmd_list(args):
    icons = installed_icons()
    profiles = installed_profiles()
    if not icons and not profiles:
        print("nothing installed")
        return 0
    for name, paths in icons.items():
        print(f"{name}  ({len(paths)} files)")
    for path in profiles:
        print(f"{path.name}  ->  {path}")
    return 0


def cmd_uninstall(args):
    if args.all:
        names = list(installed_icons())
        profiles = installed_profiles()
    else:
        key = _key_from_args(args)
        names = [icon_name(key)]
        candidate = konsole_profile_dir() / profile_filename(key)
        profiles = [candidate] if candidate.exists() else []

    removed = 0
    for name in names:
        for path in remove_icon(name):
            print(f"removed {path}")
            removed += 1
    for path in profiles:
        path.unlink()
        print(f"removed {path}")
        removed += 1
    if not removed:
        print("nothing to remove")
    return 0


def cmd_sessions(args):
    services = list_konsole_services()
    if not services:
        print("no Konsole instance is on the session bus")
        return 1
    for service in services:
        print(service)
        for path in list_sessions(service):
            print(f"  {service}:{path}")
    return 0


BADGE_METHODS = (
    "setBadgeEnabled",
    "setBadgeText",
    "setBadgeColor",
    "setBadgeTextOnly",
    "setBadgeTransparency",
    "setBadgeFontFamily",
    "setBadgeFontSize",
)


def cmd_probe(args):
    """Report which of the two routes this Konsole build actually offers.

    setBadgeColor takes a QColor, which is not a basic D-Bus type. Konsole
    registers no metatype for it, so it may be absent from introspection even
    though the header marks it Q_SCRIPTABLE. That is exactly what this checks.
    """
    service, path = resolve_session(args.session)
    print(f"session   {service}:{path}")
    members = dbus_members(service, path)
    print(f"members   {len(members)}")
    print()
    print("badge route")
    for method in BADGE_METHODS:
        print(f"  {'yes' if method in members else 'NO '}  {method}")
    print()
    print("profile route")
    for method in ("setProfile", "profile"):
        print(f"  {'yes' if method in members else 'NO '}  {method}")
    print()
    print("not scriptable, hence no direct tab-icon route")
    print("  NO   setIconName")
    return 0


def cmd_badge(args):
    key = _key_from_args(args)
    service, path = resolve_session(args.session)
    members = dbus_members(service, path)

    if args.clear:
        dbus_call(service, path, "setBadgeEnabled", ["false"])
        print(f"badge cleared on {service}:{path}")
        return 0

    label = args.label or badge_label(key)
    dbus_call(service, path, "setBadgeText", [label])
    dbus_call(service, path, "setBadgeEnabled", ["true"])
    print(f"badge text  {label}")

    colour = hex_colour(identicon_colour(key, args.saturation, args.lightness))
    if "setBadgeColor" in members:
        dbus_call(service, path, "setBadgeColor", [colour])
        print(f"badge colour {colour}")
    else:
        print(f"badge colour {colour} NOT APPLIED - setBadgeColor absent from introspection")
        print("             QColor has no D-Bus metatype registered in Konsole")
    return 0


def cmd_profile(args):
    key = _key_from_args(args)
    install_icon(key, **_render_kwargs(args))
    target = install_profile(key, parent=args.parent)
    name = profile_name(key)
    print(f"icon     {icon_name(key)}")
    print(f"profile  {name}")
    print(f"         {target}")

    if not args.apply:
        print()
        print("re-run with --apply to switch the current tab to it")
        return 0

    service, path = resolve_session(args.session)
    dbus_call(service, path, "setProfile", [name])
    active = dbus_call(service, path, "profile").strip()
    print(f"applied  {service}:{path}")
    print(f"now on   {active or '(empty)'}")
    if active != name:
        print()
        print("setProfile matches against already-loaded profiles and no-ops on a")
        print("miss. A profile written after Konsole started is not loaded yet;")
        print("open Settings, Manage Profiles, or restart Konsole, then retry.")
        return 1
    return 0


def cmd_demo(args):
    key = _key_from_args(args)
    print(f"=== {key} ===")
    print(render_ansi(key))
    print()
    for step, handler in (("probe", cmd_probe), ("badge", cmd_badge), ("profile", cmd_profile)):
        print(f"--- {step} ---")
        try:
            handler(args)
        except DBusError as error:
            print(f"skipped: {error}")
        print()
    return 0


def cmd_doctor(args):
    print(f"qdbus            {find_qdbus() or 'NOT FOUND'}")
    print(f"gdbus            {find_gdbus() or 'NOT FOUND'}")
    print(f"icon theme root  {icon_theme_root()}")
    print(f"profile dir      {konsole_profile_dir()}")
    print(f"in Konsole       {'yes' if os.environ.get('KONSOLE_DBUS_SESSION') else 'no'}")
    for variable in ("KONSOLE_DBUS_SERVICE", "KONSOLE_DBUS_SESSION", "KONSOLE_VERSION"):
        print(f"  {variable}={os.environ.get(variable, '')}")
    print(f"icons installed  {len(installed_icons())}")
    print(f"profiles written {len(installed_profiles())}")
    try:
        services = list_konsole_services()
        print(f"konsole services {', '.join(services) if services else 'none'}")
    except DBusError as error:
        print(f"konsole services unavailable: {error}")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="claude-state-identicon",
        description="Per-project identicons for Konsole tabs, over the session D-Bus interface.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(target, *, path=True, render=False, session=False):
        if path:
            target.add_argument("path", nargs="?", help="project path (default: cwd)")
        if render:
            target.add_argument("--saturation", type=float, default=0.55)
            target.add_argument("--lightness", type=float, default=0.50)
            target.add_argument("--background", help="six digit hex; default transparent")
        else:
            target.set_defaults(saturation=0.55, lightness=0.50, background=None)
        if session:
            target.add_argument("--session", help="service:/Sessions/N; default from the environment")
        else:
            target.set_defaults(session=None)

    show = sub.add_parser("show", help="print the derived names and a terminal preview")
    add_common(show, render=True)
    show.set_defaults(func=cmd_show)

    render = sub.add_parser("render", help="write one identicon image")
    add_common(render, render=True)
    render.add_argument("--size", type=int, default=256)
    render.add_argument("--format", choices=("png", "svg"), default="png")
    render.add_argument("--out", default="-", help="output file, or - for stdout")
    render.set_defaults(func=cmd_render)

    install = sub.add_parser("install", help="install the identicon into the user icon theme")
    add_common(install, render=True)
    install.set_defaults(func=cmd_install)

    listing = sub.add_parser("list", help="list installed identicons and profiles")
    add_common(listing, path=False)
    listing.set_defaults(func=cmd_list)

    uninstall = sub.add_parser("uninstall", help="remove installed identicons and profiles")
    add_common(uninstall)
    uninstall.add_argument("--all", action="store_true")
    uninstall.set_defaults(func=cmd_uninstall)

    sessions = sub.add_parser("sessions", help="list Konsole sessions on the bus")
    add_common(sessions, path=False)
    sessions.set_defaults(func=cmd_sessions)

    probe = sub.add_parser("probe", help="report which D-Bus methods this Konsole exposes")
    add_common(probe, path=False, session=True)
    probe.set_defaults(func=cmd_probe)

    badge = sub.add_parser("badge", help="route one: set the session badge")
    add_common(badge, render=True, session=True)
    badge.add_argument("--label", help="override the derived one or two character label")
    badge.add_argument("--clear", action="store_true", help="disable the badge instead")
    badge.set_defaults(func=cmd_badge)

    profile = sub.add_parser("profile", help="route two: generate a profile carrying the icon")
    add_common(profile, render=True, session=True)
    profile.add_argument("--parent", default="FALLBACK/", help="profile to inherit from")
    profile.add_argument("--apply", action="store_true", help="switch the session to it")
    profile.set_defaults(func=cmd_profile)

    demo = sub.add_parser("demo", help="probe, then exercise both routes on one session")
    add_common(demo, render=True, session=True)
    demo.add_argument("--label", default=None)
    demo.add_argument("--parent", default="FALLBACK/")
    demo.set_defaults(func=cmd_demo, clear=False, apply=True)

    doctor = sub.add_parser("doctor", help="environment report")
    add_common(doctor, path=False)
    doctor.set_defaults(func=cmd_doctor)

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except DBusError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
