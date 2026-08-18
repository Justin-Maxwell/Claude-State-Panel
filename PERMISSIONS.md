# Permissions

What working in this repository causes Claude to run, and why.

**Documentation only.** Nothing here is installed automatically, and this file
is not read by anything. It exists so that the reason for a rule survives the
prompt that requested it — a permission dialog vanishes on click and takes its
text with it, so anything worth thinking about has to live outside the prompt.

## Why this is not `.claude/settings.local.json`

That file exists, is machine-local, is not committed, and has accreted 58 rules
by clicking "don't ask again" over several months. It records *that* something
was allowed and never *why*, includes one-off commands that will never run again
(a specific Konsole D-Bus service number, a merge in a scratch directory that no
longer exists), and cannot be reviewed by anyone else.

This file is the deliberate version. The two are expected to disagree; this one
is the one to trust about intent.

## Routine, and worth allowing

| rule | why |
|---|---|
| `Bash(python3 *)` | The test suite, and every probe. Established practice here is to answer questions with `python3 -c` rather than shell — `shutil.which` instead of `which`, `json.loads` to check a config parses — because it is one allowlisted call instead of several prompts. |
| `Bash(just test:*)` | The suite. `just test-tz` runs it under a shifted timezone. |
| `Bash(just doctor:*)` | Environment diagnosis; read-only. |
| `Bash(git add:*)`, `Bash(git commit:*)` | Ordinary version control. Deliberately **not** `git push` — see below. |
| `Bash(node *)` | Only for `identicon/reference/`, where the vendored identicon.js is executed to regenerate or check `vectors.json`. This is the conformance apparatus; it runs a library committed here, not anything fetched. |

## Installs onto the machine, so decide once and knowingly

| rule | what it changes |
|---|---|
| `Bash(just install-cli:*)` | Symlinks `bin/claude-state-panel` into `~/.local/bin`. |
| `Bash(just install-plasmoid:*)` | Registers the widget with Plasma. Also `upgrade-` and `uninstall-`. |
| `Bash(just identicon-install:*)` | Writes PNGs into the user icon theme, and a Konsole profile. `identicon-uninstall` reverses it. |

These leave state behind after the session ends. That is their purpose, and the
reason they are listed apart from the routine set rather than mixed in with it.

## Deliberately not allowlisted

- **`git push`.** This repository is 49 commits ahead of its remote as a matter
  of routine. Pushing is a decision, and publishing is not reversible in the way
  a local commit is.
- **Anything with a network fetch**, beyond the specific `WebFetch` domains a
  task actually needs. The product itself makes no network calls of any kind,
  which is a stated design constraint rather than an accident, and the tooling
  around it should not quietly acquire the habit.
- **Compound commands.** A call chained with `&&` or `;` cannot be reduced to a
  reusable prefix, so it prompts every time and never accumulates into a rule.
  One command per call, always.

## The identicon

Since v0.1 of the `claude-colophon` plugin, installing an identicon into a
repository is that plugin's business rather than this one's, and its permission
needs are documented in its own `PERMISSIONS.md`. What remains here is the
conformance apparatus — the vendored identicon.js and its pinned vectors — which
needs only `Bash(node *)` and the test suite.
