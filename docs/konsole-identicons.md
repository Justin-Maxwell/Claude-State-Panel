# Konsole project identicons

A per-tab marker identifying which project a Konsole tab belongs to, derived
from its working directory. Adjacent to the panel widget rather than part of
it: the panel answers *is anything waiting on me*, this answers *which project
is this tab*.

Three routes exist. Two work on a stock Konsole and are implemented in
`identicon/repository-identicon.py`. The third is the one originally scoped —
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
identicon/repository-identicon.py badge          # marks the tab you run it in
identicon/repository-identicon.py badge --clear
```

**Caveat, unresolved off-machine.** `setBadgeColor` takes a `QColor`, which is
not a basic D-Bus type, and `Session.cpp` calls `qDBusRegisterMetaType` nowhere.
The method may therefore be missing from introspection despite the
`Q_SCRIPTABLE` marking. The `probe` subcommand reports exactly this, and `badge`
degrades to text-only with a warning rather than failing:

```
identicon/repository-identicon.py probe
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
identicon/repository-identicon.py install
identicon/repository-identicon.py profile --apply
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

Specified in `docs/project-identicon-spec.md`, which is shared with the panel
and with the return-of-control hook so that a tab, a glyph and a terminal
banner cannot disagree about a project. Not restated here.

The two points that bear on Konsole specifically:

- The key is the **git remote**, normalised to `host/owner/repo`, not the
  working directory. A tab that `cd`s within a project keeps its identicon;
  two checkouts of one project share one.
- Konsole's profile `Icon` is a **theme name, not a path**, so the icon has to
  be installed before the profile can reference it. `profile` does both.

The identicon is always computed. `.repository-identicon` at the repository
top level overrides the derived key, and holds a seed rather than an image.

## Command line

Install is manual for now — no hook wiring, by design.

```
just identicon-show                 # derived names and a terminal preview
just identicon-install              # into the user icon theme
just identicon-probe                # which D-Bus methods this Konsole exposes
just identicon-demo                 # probe, then exercise both routes
just identicon-uninstall            # remove icons and profiles for the cwd

identicon/repository-identicon.py doctor
identicon/repository-identicon.py sessions
identicon/repository-identicon.py render . --format svg --size 256 --out x.svg
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
