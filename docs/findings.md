# Findings

One entry per `⟨verify⟩` item from the specification, recorded when resolved.

Where the spec and reality disagree, reality wins — but the disagreement is
recorded here rather than silently adapted to. This is the artefact that makes
the next session's reasoning sound.

## Entry format

```
## N. <the question>

- **Assumed:** what the spec claimed, and where.
- **Observed:** what actually happened.
- **Test:** the exact command, payload, or interaction used.
- **Date:** YYYY-MM-DD
- **Consequence:** what changed in the spec or the code as a result.
```

## Open

One resolved. Eight outstanding from spec §13, plus one new item.

| # | Question | Phase |
|---|---|---|
| 1 | Does `PreToolUse` fire for `AskUserQuestion`, and `PostToolUse` only after the answer? | 0 |
| 2 | What, if anything, fires on Esc interrupt? | 0 |
| 4 | Does `Notification`/`idle_prompt` fire after an interrupt? | 0 |
| 10 | Can a non-interactive session be reliably distinguished from an interactive one? | 0 |
| 5 | Correct Plasma 6 QML import and API for the executable data engine | 2 |
| 6 | Konsole D-Bus object paths, interfaces, and the PID field matching a tab | 3 |
| 7 | Can a non-focused process raise a Konsole window under KWin on Wayland? | 3 |
| 8 | Does Konsole honour an OSC title sequence given the tab-title format? | 3 |
| 9 | Reliable way to derive a session's `tty` from `/proc` | 0 |

Items 1, 2, 4, 9 and 10 block Phase 1. Phase 2 must not begin with any Phase 0
item unresolved.

## Resolved

## 3. In exec form, is `os.getppid()` the `claude` process?

- **Assumed:** yes, spec §4.3 — "in exec form the writer's `os.getppid()` **is
  the `claude` process**, with no `sh -c` in between", making process identity a
  one-line read rather than a `/proc` ancestry walk. Marked `⟨verify⟩`.
- **Observed:** confirmed. Every probe record written from a hook registered
  with `"args": []` reports `ppid_comm='claude'`. The grandparent is `bash`,
  which is the Konsole shell, not an intervening `sh -c`.
- **Test:** registered `probe/probe.sh` on ten events in exec form, then read
  `/proc/$PPID/comm` from inside the hook. 7 records, 100% agreement.
- **Date:** 2026-08-14
- **Consequence:** §4.5 stands as written. `claude_pid = os.getppid()`. No
  `/proc` walk needed for process identity. Note the walk is still required for
  `konsole_pid` (§7.2), which is further up the tree.

## A. Hook registration takes effect on an already-running session

- **Assumed:** not in the spec. This session assumed a restart would be needed,
  reasoning that Claude Code snapshots hook config at session start for safety.
- **Observed:** false. Hooks fired on the very next tool call after
  `~/.claude/settings.json` was written, with no restart and no new session.
- **Test:** wrote the registration mid-session; the immediately following `Edit`
  and `Bash` calls appear in the probe output.
- **Date:** 2026-08-14
- **Consequence:** install (§10) does not need to tell the user to restart.
  Equally, a bad writer takes effect immediately — the exit-0-unconditionally
  invariant (§4.2) is load-bearing from the moment of install, not from the next
  session.

## C. `matcher` is not present in the hook payload

- **Assumed:** spec §4.4, `StopFailure` — "Store the matcher value in
  `error_kind` (`rate_limit`, `overloaded`, `billing_error`, …)". This reads as
  though the writer can take the matcher off stdin.
- **Observed:** `matcher` is null on every record, on every event, including
  `Notification` where two distinct matchers (`idle_prompt`,
  `permission_prompt`) are known to exist. The matcher is a *config-side
  selector* that decides whether a handler runs; it is not passed to it.
- **Test:** 27 records across two sessions, all events. `.matcher` extracted by
  the probe; null throughout. The `Notification` record fired 60s after `Stop`,
  which identifies it as `idle_prompt` by timing alone.
- **Date:** 2026-08-14
- **Consequence:** **§4.4 and §10.2 need amending.** `error_kind` cannot be read
  from the payload. It must instead come from *matcher-specific registrations* —
  register `StopFailure` once per matcher, each passing the kind as a literal
  argument:

  ```json
  {"matcher": "rate_limit",
   "hooks": [{"type": "command", "command": ".../claude-state-writer.py",
              "args": ["--error-kind", "rate_limit"]}]}
  ```

  This also means the set of recognised `error_kind` values is fixed at install
  time rather than discovered at runtime, so an unregistered failure kind yields
  `error` with a null `error_kind`. The writer must handle that.

  Same reasoning would apply to distinguishing `Notification` matchers, if
  `Notification` is ever adopted as the interrupt backstop (open question 4).

## D. `idle_prompt` fires exactly 60s after `Stop`

- **Assumed:** spec §4.4 — `idle_prompt` has a 60s delay and "would only add
  latency" versus using `Stop` directly.
- **Observed:** confirmed precisely. `Stop` at 18:36:32, `Notification` at
  18:37:32.
- **Date:** 2026-08-14
- **Consequence:** the decision to drive `waiting-input` from `Stop` rather than
  `Notification` is empirically justified — it is a full minute faster. Leaves
  `Notification` available purely as the interrupt backstop.

## B. `PostToolBatch` fires after single tool calls, not only parallel batches

- **Assumed:** spec §4.4 — "Fires after a parallel batch resolves."
- **Observed:** it fires after a lone `Edit` and after a lone `Bash`, each with
  no sibling call in the batch. Sequence per tool is consistently
  `PreToolUse` → `PostToolUse` → `PostToolBatch`.
- **Test:** probe output for single-tool turns, 2026-08-14.
- **Consequence:** harmless for the transition table, since `PostToolUse` and
  `PostToolBatch` both resolve to `thinking`. But it means `PostToolBatch` is
  not a reliable signal that a *parallel* batch occurred, should anything later
  want to know that.
