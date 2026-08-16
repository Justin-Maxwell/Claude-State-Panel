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
  Claude Code                              Plasma panel
  ───────────                              ────────────
  claude agents --json ──▶ [1] evaluator ──▶ [2a] compact glyphs
  (first-party CLI)        (all logic)       [2b] popup list
                                 │           [2c] doctor CLI
                                 └──────────▶ (identical output)
```

1. **Evaluator** — `evaluator/claude-state-eval.py`. The only place truth is
   computed: classification, priority, ordering, slots, overflow, labels.
2. **Renderers** — three views over one evaluator output. None recomputes
   anything, so the panel and `doctor` cannot disagree.

**There is no writer and no state file.** Both existed to reconstruct session
state from a stream of hook events, and both are gone: `claude agents --json`
reports the state directly. What went with them is not just code but three whole
classes of bug — a crashed session leaving an uncloseable record, an Esc
interrupt freezing a record mid-transition, and an escaped question claiming
"needs your answer" forever with no timeout able to fix it. A session that dies,
is interrupted, or has its question dismissed simply stops being reported that
way on the next poll. See findings I, 2 & 4, and N.

The hook path remains fully specified in `docs/findings.md` as the fallback if
the CLI — a research preview — is ever withdrawn.

## Status

Phase 1 complete as of 2026-08-16. `just doctor` renders live sessions today.

```
   slot   state               label                      age  pid
   --------------------------------------------------------------
   0    ! waiting-permission  Clautana (tana)             8m  42984
   1    ? waiting-answer      Glyph-Hunter             1h19m  6173
   2    ○ idle                Sentry-MCP                  5m  48616
   3    ○ idle                Clautana (Foreign)          5m  50001

  overflow: +2 ●  (highest hidden state: working)
```

| Phase | Deliverable | State |
|---|---|---|
| 0 | `probe/` harness; resolve every `⟨verify⟩` item touching hooks | **Complete for Phase 1 purposes** — probe live, 13 findings, every blocker resolved |
| 1 | evaluator + `doctor`, fully testable headless | **Done** — 63 tests, all live, green under three timezones |
| 2 | plasmoid compact + popup; click copies `cwd` | Not started |
| 3 | Konsole tab focus via D-Bus | Not started |
| 4 | `error` / `rate_limit` rendering | Not started |

### The architecture decision that now precedes Phase 1

A prior-art sweep on 2026-08-16 turned up two things that bear on whether Phase 1
should be built as specified.

**1. `claude agents --json` already reports interactive session state.** The
spec's whole inference layer — writer, state file, slot bookkeeping, fifteen hook
registrations — exists because Claude Code was believed to expose no queryable
state. On version 2.1.233 it does, for interactive sessions, including `kind`,
`pid`, `cwd`, `status` and `waitingFor`. That is most of what the evaluator was
going to compute, reported as *state* rather than inferred from event edges,
which would dissolve the crash-reaping and interrupt-freezing problems entirely.
It is a research preview, so it trades stability for simplicity. Finding N.

**2. One Plasma project already shares this purpose**:
[AgentDiode](https://github.com/emreartz/AgentDiode), announced 2026-07-28. It is
a tray application rather than a panel widget, covers four agents, and is four
commits old — but it is real, MIT, and takes the same privacy stance. Every
other Claude Plasma widget found is a quota widget, so that half of the README's
premise still holds. Finding O.

Neither is a reason to stop; both are reasons not to start Phase 1 on autopilot.

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
working, the longest being 116.8s. This is confirmed behaviour, not a local
quirk: `Stop` is documented not to run on user interrupt, and the request for an
interrupt event is open and unanswered (finding M).

**One known limitation, recorded before it is built rather than after.** An
`AskUserQuestion` that the user escapes rather than answers is indistinguishable
from one still waiting — waiting indefinitely is that state's *correct*
behaviour, so no timeout can separate them. The panel would report "needs your
answer" for a question that no longer exists. Two untested escapes are noted in
finding 2 & 4; until one works, this state is the widget's weakest claim.

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
