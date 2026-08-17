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
import base64
import colorsys
import hashlib
import json
import os
import pathlib
import shutil
import struct
import subprocess
import sys
import zlib

# Bump when the key resolution, the grid, or the colour rule changes. Any bump
# changes every identicon, so it is not a thing to do casually.
SPEC_VERSION = 1

# Fixed inputs for the conformance vectors in docs/project-identicon-spec.md.
# Chosen to exercise each key source and the awkward shapes: a bare host, a
# nested group, unicode, and the empty-ish edges.
CONFORMANCE_KEYS = (
    "github.com/justin-maxwell/claude-state-panel",
    "github.com/owner/repo",
    "gitlab.com/group/sub/repo",
    "codeberg.org/a/b",
    "/home/justin/Code/Projects/Claude-State-Panel",
    "/",
    "project-with-a-committed-seed",
    "Ünicode/pröject",
)

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

# An optional one-line seed at the repository top level, overriding the derived
# key. Committing it makes a project's identicon travel with the repository.
OVERRIDE_FILENAME = ".claude-state-identicon"


def normalise_key(path):
    """Reduce a filesystem path to a stable string.

    Expanded, made absolute, and stripped of any trailing separator, so that
    `~/src/foo`, `~/src/foo/` and a relative path to the same place all agree.

    This is the *fallback* key. Prefer resolve_key, which reaches the repository
    identity first — a path is not stable across machines, containers, or the
    per-session git worktrees the desktop app creates.
    """
    expanded = os.path.expanduser(str(path))
    absolute = os.path.abspath(expanded)
    return absolute.rstrip(os.sep) or os.sep


def normalise_remote_url(url):
    """Reduce a git remote URL to `host/owner/repo`, lowercased.

    Every way of naming one repository must collapse to one key, so an SSH
    checkout and an HTTPS checkout of the same project share an identicon:

        git@github.com:Owner/Repo.git
        https://github.com/Owner/Repo.git
        https://token@github.com/Owner/Repo
        ssh://git@github.com:2222/Owner/Repo.git   ->  github.com/owner/repo

    The host is kept, so `github.com/a/b` and `gitlab.com/a/b` stay distinct.
    Returns None for a local-path remote, which is no more portable than the
    working directory and so earns no special treatment.
    """
    if not url:
        return None
    url = url.strip().rstrip("/")
    if not url or url.startswith("/") or url.startswith("file://"):
        return None

    if "://" in url:
        scheme, _, rest = url.partition("://")
        if scheme.lower() == "file":
            return None
        authority, _, path = rest.partition("/")
    elif ":" in url:
        # scp-like: [user@]host:path
        authority, _, path = url.partition(":")
    else:
        return None

    if "@" in authority:
        authority = authority.rpartition("@")[2]
    host = authority.partition(":")[0]  # drop any port

    path = path.strip("/")
    if path.lower().endswith(".git"):
        path = path[: -len(".git")]

    parts = [part for part in path.split("/") if part]
    if not host or not parts:
        return None
    return "/".join([host] + parts).lower()


def _git(args, cwd):
    """Run a git command, returning stripped stdout or None if it fails."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(cwd), *args], capture_output=True, text=True
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def repo_toplevel(path):
    """The working tree root, or None outside a repository.

    In a worktree this is the worktree's own root, not the main checkout — which
    is exactly why it is not the key.
    """
    return _git(["rev-parse", "--show-toplevel"], path)


def repo_remote_url(path):
    """The origin URL, falling back to whichever remote is listed first."""
    url = _git(["remote", "get-url", "origin"], path)
    if url:
        return url
    remotes = _git(["remote"], path)
    if not remotes:
        return None
    return _git(["remote", "get-url", remotes.splitlines()[0].strip()], path)


def override_key(directory):
    """The committed seed at `directory`, if there is a usable one."""
    if not directory:
        return None
    candidate = pathlib.Path(directory) / OVERRIDE_FILENAME
    try:
        text = candidate.read_text()
    except (OSError, UnicodeDecodeError):
        return None
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line
    return None


def resolve_key(path=None, explicit=None):
    """Return (key, source) for a project directory.

    Precedence, most specific first:

      explicit   given on the command line
      override   a committed .claude-state-identicon at the repository root
      remote     host/owner/repo from the git remote -- the portable one
      toplevel   the repository root path, for a repository with no remote
      path       the directory itself, outside a repository

    Only `remote` and `override` survive being cloned somewhere else. The two
    path-shaped sources are honest fallbacks, not equivalents.
    """
    directory = normalise_key(path if path else os.getcwd())
    if explicit:
        return explicit, "explicit"

    toplevel = repo_toplevel(directory)

    committed = override_key(toplevel or directory)
    if committed:
        return committed, "override"

    if toplevel:
        remote = normalise_remote_url(repo_remote_url(directory))
        if remote:
            return remote, "remote"
        return normalise_key(toplevel), "toplevel"

    return directory, "path"


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


def identicon_hue(key):
    """Hue in degrees, from the one digest byte the grid does not consume.

    Taking it from the same digest means the colour and the pattern cannot
    drift apart.
    """
    return _digest(key)[15] * 360 // 256


def _quantise(value):
    """Round half up, not half to even.

    Specified this way because the spec has to be reimplementable in languages
    whose native rounding is half up. Python's round() is half to even, so
    following it would have made the spec quietly unportable.
    """
    return int(value * 255 + 0.5)


def identicon_colour(key, saturation=0.55, lightness=0.50):
    """Return the foreground colour as an (r, g, b) triple of 0-255 ints."""
    red, green, blue = colorsys.hls_to_rgb(
        identicon_hue(key) / 360.0, lightness, saturation
    )
    return (_quantise(red), _quantise(green), _quantise(blue))


def hex_colour(rgb):
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def short_hash(key, length=12):
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:length]


def grid_bits(key):
    """The grid as 25 characters of 0 and 1, row-major. The conformance form."""
    return "".join(
        "1" if cell else "0" for row in identicon_grid(key) for cell in row
    )


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


# --- Terminal colour --------------------------------------------------------

TRUECOLOR = "truecolor"
INDEXED = "256"
NONE = "none"
COLOUR_DEPTHS = (TRUECOLOR, INDEXED, NONE)


def resolve_colour_depth(requested=None, environ=None):
    """Pick a colour depth. NO_COLOR wins over everything, per no-color.org."""
    environ = os.environ if environ is None else environ
    if environ.get("NO_COLOR") is not None:
        return NONE
    if requested and requested != "auto":
        return requested
    if environ.get("COLORTERM", "").lower() in ("truecolor", "24bit"):
        return TRUECOLOR
    return INDEXED


def _xterm256(rgb):
    """Nearest colour in the xterm 6x6x6 cube."""
    red, green, blue = (int(component * 5 / 255 + 0.5) for component in rgb)
    return 16 + 36 * red + 6 * green + blue


def _fg(rgb, depth):
    if depth == NONE:
        return ""
    if depth == TRUECOLOR:
        return "\033[38;2;{};{};{}m".format(*rgb)
    return f"\033[38;5;{_xterm256(rgb)}m"


def _bg(rgb, depth):
    if depth == NONE:
        return ""
    if depth == TRUECOLOR:
        return "\033[48;2;{};{};{}m".format(*rgb)
    return f"\033[48;5;{_xterm256(rgb)}m"


DEFAULT_FG = "\033[39m"
DEFAULT_BG = "\033[49m"
RESET = "\033[0m"

# Cell aspect is roughly one to two, so packing two grid rows into one text row
# with an upper half block makes the identicon come out square.
HALF_BLOCK = "▀"
FILLED_BLOCK = "█"


def render_half_blocks(key, depth=TRUECOLOR, saturation=0.55, lightness=0.50):
    """The identicon as three text rows of five characters.

    Compact enough to print on every return of control without taking the
    terminal over: two grid rows per text row, the fifth row paired with blank.
    """
    grid = identicon_grid(key)
    colour = identicon_colour(key, saturation, lightness)
    lines = []
    for text_row in range(3):
        line = ""
        for column in range(GRID):
            top = grid[text_row * 2][column]
            bottom_row = text_row * 2 + 1
            bottom = grid[bottom_row][column] if bottom_row < GRID else False
            if depth == NONE:
                line += FILLED_BLOCK if top and bottom else HALF_BLOCK if top else "▄" if bottom else " "
                continue
            line += (_fg(colour, depth) if top else DEFAULT_FG)
            line += (_bg(colour, depth) if bottom else DEFAULT_BG)
            line += HALF_BLOCK
        lines.append(line + (RESET if depth != NONE else ""))
    return lines


def render_banner(key, source=None, depth=TRUECOLOR, **kwargs):
    """The compact identicon with the project name beside it."""
    rows = render_half_blocks(key, depth, **kwargs)
    colour = identicon_colour(key, kwargs.get("saturation", 0.55),
                              kwargs.get("lightness", 0.50))
    name = project_name(key)
    if depth != NONE:
        name = f"{_fg(colour, depth)}{name}{RESET}"
    labels = [name, key if source != "path" else "", ""]
    return [f"{row}  {label}".rstrip() for row, label in zip(rows, labels)]


def render_line(key, depth=TRUECOLOR, **kwargs):
    """One line: the colour, then the project name. For the tightest prompts."""
    colour = identicon_colour(key, kwargs.get("saturation", 0.55),
                              kwargs.get("lightness", 0.50))
    mark = FILLED_BLOCK
    if depth != NONE:
        mark = f"{_fg(colour, depth)}{FILLED_BLOCK}{RESET}"
    return [f"{mark} {project_name(key)}"]


# --- Inline images ----------------------------------------------------------
#
# The blocks above are an approximation. Where the terminal can take a real
# image, send the PNG itself, base64 in an escape sequence.
#
# Konsole implements the iTerm2 file protocol: Vt102Emulation::osc_put matches
# the literal "1337;File=" and then waits for the ":" terminator, so arguments
# between the two are tolerated and ignored. It also handles kitty APC graphics
# and sixel.

ITERM2 = "iterm2"
KITTY = "kitty"
BLOCKS = "blocks"
PROTOCOLS = (ITERM2, KITTY, BLOCKS)

# Native pixel size for the inline image. Konsole ignores the protocol's own
# width and height arguments, so the PNG's own size is what decides how big it
# lands: five cells of eight pixels, about two text rows tall.
INLINE_SIZE = 40


def resolve_protocol(requested=None, environ=None):
    """Pick a graphics protocol from the environment.

    Detection is by environment variable rather than by querying the terminal,
    because a hook that waits on a terminal reply can hang a turn if nothing
    answers.
    """
    environ = os.environ if environ is None else environ
    if requested and requested != "auto":
        return requested
    if environ.get("NO_COLOR") is not None:
        return BLOCKS
    if environ.get("KITTY_WINDOW_ID") or "kitty" in environ.get("TERM", "").lower():
        return KITTY
    if environ.get("KONSOLE_VERSION") or environ.get("KONSOLE_DBUS_SESSION"):
        return ITERM2
    if environ.get("TERM_PROGRAM", "") in ("iTerm.app", "WezTerm", "ghostty", "vscode"):
        return ITERM2
    return BLOCKS


def iterm2_image(png):
    """OSC 1337 File, the iTerm2 inline image protocol.

    No argument may contain a colon, since the colon is what terminates the
    argument list and begins the payload.
    """
    payload = base64.b64encode(png).decode("ascii")
    args = ";".join(["inline=1", f"size={len(png)}", "preserveAspectRatio=1"])
    return f"\033]1337;File={args}:{payload}\a"


def kitty_image(png, chunk_size=4096):
    """APC _G, the kitty graphics protocol. Chunked, as the protocol requires."""
    payload = base64.b64encode(png).decode("ascii")
    chunks = [payload[i:i + chunk_size] for i in range(0, len(payload), chunk_size)] or [""]
    out = []
    for index, chunk in enumerate(chunks):
        more = 1 if index < len(chunks) - 1 else 0
        control = f"a=T,f=100,m={more}" if index == 0 else f"m={more}"
        out.append(f"\033_G{control};{chunk}\033\\")
    return "".join(out)


def render_inline(key, protocol, size=INLINE_SIZE, **kwargs):
    """The identicon as a real image, or None if the protocol cannot carry one."""
    if protocol not in (ITERM2, KITTY):
        return None
    png = render_png(key, size, **kwargs)
    return iterm2_image(png) if protocol == ITERM2 else kitty_image(png)


def render(key, style="icon", source=None, depth=TRUECOLOR, protocol=BLOCKS,
           size=INLINE_SIZE, **kwargs):
    """Return everything to write for one identicon, trailing newline included.

    The default is the icon and nothing else — no project name, no key. The
    identicon is the message; anything beside it is the terminal's own business.
    """
    if style == "icon":
        inline = render_inline(key, protocol, size, **kwargs)
        if inline is not None:
            return inline + "\n"
        style = BLOCKS

    if style == "image":
        inline = render_inline(key, protocol if protocol != BLOCKS else ITERM2,
                               size, **kwargs)
        return (inline or "") + "\n"

    lines = _BLOCK_STYLES[style](key, source=source, depth=depth, **kwargs)
    return "".join(line + "\n" for line in lines)


_BLOCK_STYLES = {
    BLOCKS: lambda key, source=None, depth=TRUECOLOR, **kw: render_half_blocks(key, depth, **kw),
    "full": lambda key, source=None, depth=TRUECOLOR, **kw: render_ansi(key).splitlines(),
    "banner": render_banner,
    "line": lambda key, source=None, depth=TRUECOLOR, **kw: render_line(key, depth, **kw),
}

STYLES = ("icon", "image", BLOCKS, "full", "banner", "line")


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


def _resolve_from_args(args):
    return resolve_key(getattr(args, "path", None), getattr(args, "key", None))


def _key_from_args(args):
    return _resolve_from_args(args)[0]


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


SOURCE_NOTES = {
    "explicit": "given on the command line",
    "override": f"committed {OVERRIDE_FILENAME}",
    "remote": "git remote, portable across checkouts",
    "toplevel": "repository root path, no remote to use",
    "path": "not a repository, so the path is all there is",
}


def cmd_show(args):
    key, source = _resolve_from_args(args)
    print(f"key       {key}")
    print(f"source    {source}  ({SOURCE_NOTES[source]})")
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


# Hook events at which control comes back to the human. Notification is left
# out deliberately: idle_prompt fires exactly 60s after Stop, so registering it
# would print the same identicon twice, a minute apart.
RETURN_OF_CONTROL_EVENTS = ("Stop", "PermissionRequest", "Elicitation", "SessionEnd")


def payload_cwd(stream):
    """The cwd from a hook payload on stdin, or None.

    Every hook payload carries cwd, session_id and hook_event_name — the probe
    confirmed that across 27 records. Nothing else here is read, and in
    particular nothing that could carry prompt or tool text.
    """
    try:
        payload = json.load(stream)
    except (ValueError, OSError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    cwd = payload.get("cwd")
    return cwd if isinstance(cwd, str) and cwd else None


def open_output():
    """The controlling terminal if there is one, else stdout.

    A hook's stdout is not reliably shown, and for some events it is fed back to
    the model instead. The terminal is where a return-of-control marker belongs,
    so go there directly when it exists.
    """
    try:
        return open("/dev/tty", "w"), True
    except OSError:
        return sys.stdout, False


def cmd_emit(args):
    """Print the identicon. Intended for a return-of-control hook.

    Exits 0 whatever happens. A hook that fails must not disturb the session,
    and a missing identicon is not worth a broken turn.
    """
    try:
        path = args.path
        if not path and not sys.stdin.isatty():
            path = payload_cwd(sys.stdin)
        key, source = resolve_key(path, args.key)

        text = render(
            key,
            style=args.style,
            source=source,
            depth=resolve_colour_depth(args.colour),
            protocol=resolve_protocol(args.protocol),
            size=args.size,
            saturation=args.saturation,
            lightness=args.lightness,
        )

        stream, is_tty = open_output()
        try:
            stream.write(text)
            stream.flush()
        finally:
            if is_tty:
                stream.close()
    except Exception:  # noqa: BLE001 - a hook must never break the session
        pass
    return 0


def cmd_hooks(args):
    """Print the registration to paste into settings, rather than writing it.

    Deliberately not self-installing. The Phase 0 probe is registered on these
    same events right now, and silently editing settings from here could not be
    tested against a running Claude Code.
    """
    command = str(pathlib.Path(__file__).resolve())
    entry = {
        "hooks": [{
            "type": "command",
            "command": command,
            "args": ["emit", "--style", args.style],
        }]
    }
    print(json.dumps({event: [entry] for event in RETURN_OF_CONTROL_EVENTS}, indent=2))
    print()
    print("Merge into the hooks object in ~/.claude/settings.json.")
    print("Notification is omitted on purpose: idle_prompt fires 60s after Stop,")
    print("so registering both prints the same identicon twice.")
    print()
    print("The Phase 0 probe is registered on these events too. Check for a")
    print("collision before adding these, per the README.")
    return 0


def cmd_vectors(args):
    """Emit the conformance vectors another implementation can check against."""
    vectors = {
        "spec_version": SPEC_VERSION,
        "saturation": 0.55,
        "lightness": 0.50,
        "vectors": [
            {
                "key": key,
                "grid": grid_bits(key),
                "hue": identicon_hue(key),
                "rgb": list(identicon_colour(key)),
                "hex": hex_colour(identicon_colour(key)),
                "short_id": short_hash(key),
                "badge": badge_label(key),
            }
            for key in CONFORMANCE_KEYS
        ],
    }
    print(json.dumps(vectors, indent=2, ensure_ascii=False))
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
            target.add_argument("--key", help="override the derived key outright")
        else:
            target.set_defaults(key=None)
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

    emit = sub.add_parser(
        "emit",
        help="print the identicon; for a return-of-control hook",
        description="Reads a hook payload on stdin and uses its cwd. Writes to "
                    "the controlling terminal when there is one. Always exits 0.",
    )
    add_common(emit, render=True)
    emit.add_argument("--style", choices=STYLES, default="icon",
                      help="icon sends a real image where the terminal takes one")
    emit.add_argument("--protocol", choices=("auto", *PROTOCOLS), default="auto")
    emit.add_argument("--size", type=int, default=INLINE_SIZE,
                      help="inline image side in pixels")
    emit.add_argument("--colour", choices=("auto", *COLOUR_DEPTHS), default="auto")
    emit.set_defaults(func=cmd_emit)

    hooks = sub.add_parser("hooks", help="print the hook registration to paste")
    add_common(hooks, path=False)
    hooks.add_argument("--style", choices=STYLES, default="icon")
    hooks.set_defaults(func=cmd_hooks)

    vectors = sub.add_parser("vectors", help="print the conformance vectors as JSON")
    add_common(vectors, path=False)
    vectors.set_defaults(func=cmd_vectors)

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
    except BrokenPipeError:
        # Piping into head closes the pipe early. Retarget stdout at devnull so
        # the interpreter's own flush at exit does not report it a second time.
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0


if __name__ == "__main__":
    sys.exit(main())
