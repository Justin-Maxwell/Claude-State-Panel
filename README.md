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

Phase 0 in progress, as of 2026-08-16. No implementation code written yet.

| Phase | Deliverable | State |
|---|---|---|
| 0 | `probe/` harness; resolve every `⟨verify⟩` item touching hooks | **Complete for Phase 1 purposes** — probe live, 12 findings, every blocker resolved |
| 1 | writer + evaluator + `doctor`, fully testable headless | **Unblocked, not started** |
| 2 | plasmoid compact + popup; click copies `cwd` | Not started |
| 3 | Konsole tab focus via D-Bus | Not started |
| 4 | `error` / `rate_limit` rendering | Not started |

Resolved assumptions accumulate in `docs/findings.md`; observed hook sequences
in `docs/hook-events.md`. The specification itself is **not yet in this repo** —
it lives at `~/Downloads/claude-session-panel-spec.md` and still carries the
pre-rename project name throughout. Moving it to `docs/spec.md` is part of the
outstanding rename pass.

## Resuming this work

**The probe hooks are live in `~/.claude/settings.json` right now.** Every
Claude Code session on this machine writes to
`~/.local/state/claude-state-panel/hook-probe.jsonl`, including scheduled
overnight runs. Two consequences:

1. `probe/probe.sh` is installed *instead of* the writer. **Delete its eleven
   registrations before Phase 1** registers the real writer, or both will run.
2. The capture used to live in `/tmp`, which is tmpfs here. Two hard crashes on
   2026-08-15 wiped it twice, taking the 540-record base finding H reasoned
   from. It now lives under `XDG_STATE_HOME`; a third crash the same evening
   confirmed it survives a reboot — see finding I. `CLAUDE_PROBE_OUT` still
   overrides the path.
3. The capture is mode 0600 — it holds the `cwd` of every session on the machine.
   `probe.sh` sets `umask 077`; if you ever see it at 0644, something recreated
   the file outside the probe.

Each record carries an `ancestry` field: the `pid:comm` chain from the hook's
parent up to PID 1. That is where `konsole_pid` (§7.2) comes from, and it is the
basis for distinguishing a non-interactive session — **no `konsole` ancestor** —
rather than the `timeout` grandparent, which only detected one launcher. Ancestor
`cmdline` is deliberately never recorded; see the header comment for why.

To see what has accumulated:

```
probe/analyse.py                    # summary, and which planned events never fired
probe/analyse.py --sid <8-char-id>  # one session's sequence, with gaps
```

**Phase 0 has no blockers left.** All three scenarios that needed a human
arrived on 2026-08-16. An `AskUserQuestion` was answered in an unrelated session
while the probe was live, settling question 1 (finding 1). The non-interactive
session turned out to be a Plasma quota widget spawning `timeout 5 claude -p
"x"`, observed twice (finding K). And an Esc interrupt held for 380 seconds
settled questions 2 and 4 together: **nothing fires at all** — no `Stop`, no
`Notification`, no terminal event (finding 2 & 4).

That last one is the load-bearing result. An interrupted session freezes in a
transient state with a live, healthy process, so the liveness reap cannot touch
it and the staleness ceiling is the *only* mechanism that recovers it. The
ceiling therefore belongs in Phase 1, not in a later safety pass, and it must
clear 180s — measured against 882 gaps in which sessions were provably still
working, the longest being 116.8s.

**Ruled 2026-08-16: a glyph appears when Justin first types into a session, not
when the session opens.** A slot is claimed on the first `UserPromptSubmit`;
`SessionStart` creates the record but renders nothing. This meets the
"non-interactive sessions never claim a slot" requirement without detecting
anything, so open question 10 is dissolved rather than answered — there is no
interactivity test to get wrong. The accepted cost is that a session opened but
not yet typed into is invisible; it is not waiting on you, and you are looking
at it. Findings H and K.

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
