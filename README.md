# Claude State Panel

A KDE Plasma 6 panel widget showing the live state of every running Claude Code
session — one glyph per session, so a session waiting on you is visible without
the terminal being focused.

- **Plasmoid ID:** `nz.jaymax.claudestatepanel`
- **Target:** Plasma 6, Fedora, Wayland
- **Licence:** AGPL-3.0-or-later

## Why

Claude Code pauses often — awaiting a permission decision, awaiting an answer,
or simply having finished its turn. The existing signal is a `notify-send`
banner that disappears. Working across several concurrent sessions in Konsole
tabs, there is no persistent answer to "is anything waiting on me, and which
thing". This widget is that answer.

## What it deliberately does not do

- No token counting, cost estimation, or quota percentages.
- **No network calls of any kind.**
- **No access to `~/.claude/.credentials.json`** or any OAuth token.

Two quota widgets already installed on this machine were examined first. One
issues a live completion request every 15 minutes purely to read rate-limit
response headers — consuming quota to measure quota, and continuously
re-anchoring the rolling usage window so it can never lapse. Staying entirely
local removes that whole class of hazard along with all credential-handling
risk.

## Architecture

Three processes, one direction of data flow, and exactly one place where truth
is computed.

```
  Claude Code                                          Plasma panel
  ───────────                                          ────────────
  hook events ──▶ [1] writer ──▶ state file ──▶ [2] evaluator ──▶ [3a] compact glyphs
  (9 events)      (fast, dumb)   (tmpfs, JSON)   (all logic)      [3b] popup list
                                                        │          [3c] doctor CLI
                                                        └──────────▶ (identical output)
```

1. **Writer** — invoked per hook event, records raw facts, contains no policy.
2. **Evaluator** — the only component deciding liveness, staleness, and order.
3. **Renderers** — three views over one evaluator output. None recomputes
   anything, so the panel and `doctor` cannot disagree.

State lives at `$XDG_RUNTIME_DIR/claude-state-panel/state.json` — tmpfs, mode
`0600`, wiped on reboot by design.

## Status

Phase 0 in progress, as of 2026-08-14. No implementation code written yet.

| Phase | Deliverable | State |
|---|---|---|
| 0 | `probe/` harness; resolve every `⟨verify⟩` item touching hooks | **In progress** — probe live, 4 findings recorded, 3 open questions need interactive scenarios |
| 1 | writer + evaluator + `doctor`, fully testable headless | Not started — blocked on Phase 0 |
| 2 | plasmoid compact + popup; click copies `cwd` | Not started |
| 3 | Konsole tab focus via D-Bus | Not started |
| 4 | `error` / `rate_limit` rendering | Not started |

What a glyph is allowed to say is specified in `docs/state-vocabulary.md`, which
supersedes the spec's glyph and colour table: one theme role per state, tool
classes, error kinds, an intensity ramp in place of a binary stale flag,
ordinals where a project has several live sessions, and a project hue rule. It
is deliberately maximal and carries its own collapse order.

Resolved assumptions accumulate in `docs/findings.md`; observed hook sequences
in `docs/hook-events.md`. The specification itself is **not yet in this repo** —
it lives at `~/Downloads/claude-session-panel-spec.md` and still carries the
pre-rename project name throughout. Moving it to `docs/spec.md` is part of the
outstanding rename pass.

## Resuming this work

**The probe hooks are live in `~/.claude/settings.json` right now.** Every
Claude Code session on this machine writes to `/tmp/claude-hook-probe.jsonl`,
including scheduled overnight runs. Two consequences:

1. `probe/probe.sh` is installed *instead of* the writer. **Delete its eleven
   registrations before Phase 1** registers the real writer, or both will run.
2. `/tmp` is tmpfs. A reboot loses the capture. `docs/hook-events.md` holds the
   distilled record, so nothing important is only in `/tmp`.

To see what has accumulated:

```
probe/analyse.py                    # summary, and which planned events never fired
probe/analyse.py --sid <8-char-id>  # one session's sequence, with gaps
```

Three open questions need scenarios only a human can trigger — an
`AskUserQuestion` answered, an Esc interrupt left for 90s, and a non-interactive
session. They are listed with their tests in `docs/findings.md`.

## Project identicons

A deterministic visual identity for a project, derived from the project and
nothing else, so that independent tools agree without coordinating.
`docs/project-identicon-spec.md` is the shared contract; `identicon/vectors.json`
is its conformance suite. Three consumers so far:

**On every return of control.** A hook prints the identicon when a turn ends or
control comes back to you — `Stop`, `PermissionRequest`, `Elicitation`,
`SessionEnd`. The icon and nothing else: no project name, no key. Konsole takes
the iTerm2 inline image protocol, so it gets the actual PNG, base64 in an escape
sequence, at the full 5×5; terminals that can't are given a half-block
approximation instead. `Notification` is left out on purpose: `idle_prompt`
fires exactly 60s after `Stop`, so registering both would print the same mark
twice a minute apart.

```
just identicon-emit     # see it
just identicon-hooks    # the registration to paste, checked against the probe first
```

**In the panel**, as the project hue channel beneath each state glyph. See
`docs/state-vocabulary.md`.

**On a Konsole tab**, by the two compile-free routes below.

The key is the **git remote**, normalised to `host/owner/repo` — not the working
directory, because the desktop app gives each parallel session its own git
worktree and a path key would give each of them a different identity.

### Konsole

The panel answers *is anything waiting on me*; a Konsole tab marker answers
*which project is this tab*. Applied over Konsole's session D-Bus interface, by
two routes that need no compilation:

- **badge** — a coloured one or two character label over the terminal view.
- **profile** — a generated profile carrying an `Icon=`, giving a real tab-bar
  icon.

The route originally scoped, an identicon on the session toolbar, is blocked:
Konsole installs no plugin headers, so a `IKonsolePlugin` cannot be built out of
tree at all. Finding E in `docs/findings.md`.

Manual for now — nothing is wired to a hook.

```
just identicon-show        # derived names and a terminal preview
just identicon-install     # into the user icon theme
just identicon-probe       # which D-Bus methods this Konsole exposes
just identicon-demo        # probe, then exercise both routes on this tab
just identicon-uninstall
```

Full write-up, with the upstream evidence for every claim, in
`docs/konsole-identicons.md`.

## Naming

The project was renamed from `claude-session-panel` to `claude-state-panel`
after the specification was written. Project-identified names take the
`claude-state-` prefix; the word *session* is retained only where it refers to
an actual Claude Code session. The specification document still carries the old
name throughout — a rename pass over it is outstanding.

## Development

```
just              # list recipes
just test         # headless test suite, no Plasma shell required
just doctor       # render current state (Phase 1 onward)
just preview      # plasmoidviewer on the widget (Phase 2 onward)
```

No test may require a running Plasma shell or a live Claude Code session.

## Licence

AGPL-3.0-or-later. See `LICENSE`. No third-party code is vendored; `NOTICE`
records design attribution.
