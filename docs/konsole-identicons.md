# Konsole project identicons

A per-tab marker identifying which project a Konsole tab belongs to, derived
from its working directory. Adjacent to the panel widget rather than part of
it: the panel answers *is anything waiting on me*, this answers *which project
is this tab*.

Three routes exist. Two work on a stock Konsole and are implemented in
`identicon/claude-state-identicon.py`. The third is the one originally scoped —
an identicon on the session toolbar — and it is blocked.

Every claim below was checked against `KDE/konsole@master`. Nothing here is
recalled.

## Route 1 — session badge (works, no compilation)

`org.kde.konsole.Session` marks the whole badge family `Q_SCRIPTABLE`
(`src/session/Session.h`):

```
setBadgeEnabled(bool)          setBadgeText(QString)
setBadgeColor(QColor)          setBadgeTextOnly(bool)
setBadgeTransparency(int)      setBadgeFontFamily(QString)
setBadgeFontSize(int)
```

So a one or two character project label with a deterministic colour can be set
from a shell, with no C++ at all.

```
identicon/claude-state-identicon.py badge          # marks the tab you run it in
identicon/claude-state-identicon.py badge --clear
```

**Caveat, unresolved off-machine.** `setBadgeColor` takes a `QColor`, which is
not a basic D-Bus type, and `Session.cpp` calls `qDBusRegisterMetaType` nowhere.
The method may therefore be missing from introspection despite the
`Q_SCRIPTABLE` marking. The `probe` subcommand reports exactly this, and `badge`
degrades to text-only with a warning rather than failing:

```
identicon/claude-state-identicon.py probe
```

The badge paints over the terminal view, not on the toolbar, and
`Session::expandBadgeText` supports `\(session.directory)`, `\(session.title)`,
`\(session.process)` and `\(env.NAME)` placeholders if a live-updating label is
wanted later.

## Route 2 — generated profile (works, no compilation)

`setProfile` is `Q_SCRIPTABLE`; `setIconName` is not. The tab-bar icon is
therefore reachable only by generating a profile that carries an icon and
switching the session to it.

`Profile.cpp` puts the key in the `[General]` group:

```cpp
{Icon, "Icon", GENERAL_GROUP, QLatin1String("utilities-terminal")},
```

The value is a **theme icon name**, not a path, so the identicon must be
installed into the user's icon theme first. `install` writes PNGs at every
standard size plus a scalable SVG into `$XDG_DATA_HOME/icons/hicolor`, which
merges with the system theme, so no `index.theme` of our own is needed.

```
identicon/claude-state-identicon.py install
identicon/claude-state-identicon.py profile --apply
```

The generated profile declares `Parent=FALLBACK/` and sets nothing but `Name`
and `Icon`, so switching to it changes the icon and nothing else.

**Two caveats, both unresolved off-machine.**

`Session::setProfile` matches by name against
`ProfileManager::instance()->allProfiles()` and silently does nothing on a miss:

```cpp
void Session::setProfile(const QString &profileName)
{
    const QList<Profile::Ptr> profiles = ProfileManager::instance()->allProfiles();
    for (const Profile::Ptr &profile : profiles) {
        if (profile->name() == profileName) {
            SessionManager::instance()->setSessionProfile(this, profile);
        }
    }
}
```

A profile written after Konsole started may not be in that list. `profile
--apply` reads `profile()` back and reports the mismatch rather than claiming
success. Separately, `QIcon::fromTheme` caches, so a brand new icon may not
appear until Konsole restarts.

## Route 3 — session toolbar identicon (blocked)

This was the mechanism scoped in the prior session, and its Konsole-side
reasoning is correct:

- `desktop/sessionui.rc` is at `version="36"`; `sessionToolbar` carries only
  `edit_copy`, `edit_paste`, `edit_find`, `hamburger_menu`.
- `open-browser` is a plain `QAction` — `collection->addAction(QStringLiteral(
  "open-browser"), this, &SessionController::openBrowser)` — present in the File
  menu and `session-popup-menu` but not the toolbar, so a local `sessionui.rc`
  at a higher version must add it.
- It is the right host: `monitor-activity` is a `KToggleAction` whose checked
  frame would fight a painted icon.
- Each `SessionController` owns its own actions, so `setIcon` is inherently
  per-tab, and `IKonsolePlugin::activeViewChanged(SessionController*,
  MainWindow*)` hands the controller over after the toolbar exists.
- `SessionController::currentDir()` returns the session working directory, and
  `currentDirectoryChanged` catches a `cd` inside an already-active tab.

**What blocks it: Konsole ships no out-of-tree plugin SDK.** `src/CMakeLists.txt`
installs the libraries with the link symlink suppressed and installs no headers
at all:

```cmake
install(TARGETS konsoleprivate ${KDE_INSTALL_TARGETS_DEFAULT_ARGS} LIBRARY NAMELINK_SKIP)
install(TARGETS konsoleapp     ${KDE_INSTALL_TARGETS_DEFAULT_ARGS} LIBRARY NAMELINK_SKIP)
```

`IKonsolePlugin.h`, `SessionController.h` and `MainWindow.h` are unreachable
outside the source tree. Building the plugin means building against a Konsole
checkout — effectively a maintained fork — and rebuilding it every KDE Gear
release anyway, because plugin discovery gates the plugin's `major.minor`
against `RELEASE_SERVICE_VERSION`.

Not worth it for an icon, given routes 1 and 2. Revisit only if upstream starts
installing a plugin SDK.

## Identicon derivation

GitHub-style, and pinned by `tests/test_identicon.py` rather than by assertion.

### The key

The identicon is **always computed**, never stored as an image. What varies is
the key it is computed from, resolved most specific first:

| Source | Key | Portable |
|---|---|---|
| `explicit` | whatever `--key` says | — |
| `override` | first non-comment line of `.claude-state-identicon` at the repo root | yes, if committed |
| `remote` | `host/owner/repo` from the git remote | **yes** |
| `toplevel` | the repository root path, for a repo with no remote | no |
| `path` | the directory, outside a repository | no |

`show` prints which source was used, because a project silently falling back to
a path key is the failure mode worth seeing.

**The remote is the right key, and the path is not.** A path is not stable
across machines, containers, cloud sessions, or — decisively — the per-session
git worktrees the desktop app creates for parallel sessions. A worktree keeps
the same `origin` but gets its own top level, so a path-derived key would give
every parallel session in one project a *different* identicon. That is precisely
backwards: those sessions share a project, and the panel distinguishes them by
ordinal instead. See `docs/state-vocabulary.md`.

A session started in a subdirectory has the same problem and the same fix.

Remote URLs are normalised so that every spelling of one repository collapses to
one key — SSH and HTTPS, with or without `.git`, with or without embedded
credentials, with or without a port. The host is kept, so `github.com/a/b` and
`gitlab.com/a/b` stay distinct. A local-path remote is refused, since it is no
more portable than the working directory.

### Compute, or store?

Compute. Storage cannot be the primary source: an identicon has to exist for
every session, including ones in repositories you have never touched and could
not commit to. Anything stored can only ever be an override.

The override that does exist is `.claude-state-identicon` at the repository top
level, holding a **seed string, not an image**. Sizes, themes and formats stay
generated, so a stored seed cannot drift from what the renderer produces.
Committing it makes a project's identicon travel with the repository; leaving it
uncommitted keeps it local. Both work, and neither is required.

### The pattern

- `md5(key)`. Bytes 0–14 fill the left three columns of a 5×5 grid, one byte per
  cell, filled when even. Columns 0 and 1 mirror onto 4 and 3, so every
  identicon is vertically symmetric.
- Byte 15 gives the hue, at fixed saturation and lightness, so the colour and
  the pattern cannot drift apart.
- Background is transparent by default, which suits a dark panel and a light
  one equally.

This is *GitHub-style*, not byte-for-byte GitHub output.

Derived from the same key: the icon theme name
(`claude-state-identicon-<sha256[:12]>`), the profile display name
(`<project> [<sha256[:6]>]`, so two projects sharing a basename stay distinct),
and the badge label (initials where the name has separators, otherwise the
leading two characters, upper-cased).

## Command line

Install is manual for now — no hook wiring, by design.

```
just identicon-show                 # derived names and a terminal preview
just identicon-install              # into the user icon theme
just identicon-probe                # which D-Bus methods this Konsole exposes
just identicon-demo                 # probe, then exercise both routes
just identicon-uninstall            # remove icons and profiles for the cwd

identicon/claude-state-identicon.py doctor
identicon/claude-state-identicon.py sessions
identicon/claude-state-identicon.py render . --format svg --size 256 --out x.svg
```

The session to act on is taken from `KONSOLE_DBUS_SERVICE` and
`KONSOLE_DBUS_SESSION`, which `Session.cpp` exports into every session's
environment, so running the tool inside the tab you want marked needs no
arguments. `--session service:/Sessions/N` overrides.

## Open questions

Only reachable on a machine running Konsole.

1. Is `setBadgeColor` present in introspection, or does the unregistered
   `QColor` metatype drop it? `probe` answers this.
2. Does `ProfileManager` pick up a `.profile` written after Konsole started, or
   is a restart required?
3. Does `QIcon::fromTheme` find a newly installed hicolor icon without a cache
   rebuild, and does the scalable SVG resolve or only the PNGs?
4. Does the badge remain legible at the sizes and transparencies the tab
   actually uses?

## Relation to the panel

Item 6 in `findings.md` — Konsole D-Bus object paths and the PID field matching
a tab — is Phase 3 work for tab focus. The `sessions` and `probe` subcommands
here map that same surface, so whatever they establish feeds straight into it.
