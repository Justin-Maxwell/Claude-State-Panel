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

Three resolved (3, 9, and 7.2's `konsole_pid` as a side effect). Six outstanding.

| # | Question | Phase | State |
|---|---|---|---|
| 1 | Does `PreToolUse` fire for `AskUserQuestion`, and `PostToolUse` only after the answer? | 0 | **needs Justin** — answer one |
| 2 | What, if anything, fires on Esc interrupt? | 0 | **needs Justin** — interrupt, wait 90s |
| 4 | Does `Notification`/`idle_prompt` fire after an interrupt? | 0 | **needs Justin** — same scenario as 2 |
| 10 | Can a non-interactive session be reliably distinguished? | 0 | open as detection; may be **dissolvable** — finding H |
| 5 | Correct Plasma 6 QML import and API for the executable data engine | 2 | not started |
| 6 | Konsole D-Bus object paths, interfaces, and the PID field matching a tab | 3 | not started |
| 7 | Can a non-focused process raise a Konsole window under KWin on Wayland? | 3 | not started |
| 8 | Does Konsole honour an OSC title sequence given the tab-title format? | 3 | not started |

**1, 2 and 4 are the only true Phase 1 blockers**, and all three are one
five-minute sitting at the keyboard. 9 is resolved (finding G); 10 need not be
answered at all if the slot rule in finding H is accepted.

Phase 2 must not begin with any Phase 0 item unresolved.

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

## E. `source` does not distinguish a non-interactive session

- **Assumed:** the previous session expected the `SessionStart` `source` field to
  answer open question 10 — that a scheduled run would report something other
  than an interactive session does.
- **Observed:** it does not. Both sessions report `source: "startup"`. The
  scheduled run's `SessionEnd` carries `reason: "other"`, which the interactive
  session has no counterpart for yet, but a reason on the *end* event is useless
  for a decision that must be made at session *start*.
- **Test:** 2026-08-15, records for sessions `e7519d22` (scheduled, `cwd`
  `/home/justin`, lived 0.92s, no `UserPromptSubmit`, no tool calls) and
  `a9c23e29` (interactive, `cwd` the repo).
- **Consequence:** open question 10 stays open, minus one candidate. §6 cannot
  read non-interactivity off the payload.

  One candidate remains, from the same records: the scheduled session's
  *grandparent* is `timeout`, where the interactive session's is `bash`.

  ```
  e7519d22  ppid_comm='claude'  gpid_comm='timeout'
  a9c23e29  ppid_comm='claude'  gpid_comm='bash'
  ```

  Treat this as weak. It detects one particular scheduling wrapper, not
  non-interactivity as such — a run launched without `timeout`, or an
  interactive session started from something other than a shell, both defeat it.
  It also collides with §7.2, which walks the same ancestry looking for
  `konsole_pid`; absence of a Konsole ancestor is likely the sounder test, and is
  the one worth designing against. Unconfirmed either way.

  The run fired 60s after boot. I looked for what launched it and **could not
  establish it.** Ruled out: user and system systemd timers, `crontab`, XDG
  autostart (`~/.config/autostart` and `/etc/xdg/autostart`), shell profiles,
  `statusLine`, and Claude Code routines — `routineFiredWatermark` in
  `~/.claude.json` last fired 2026-06-28. The daemon log's last entry is
  2026-08-14T00:45, so the daemon did not spawn it either.

  The only `timeout … claude -p` strings on the machine are permission *rules*
  in `~/.claude/settings.local.json`, added 2026-08-13 while testing `claude -p`.
  Rules do not launch anything.

  So "scheduled" is an assumption, not a finding. What is established: the
  session ran under a `timeout` grandparent, in `/home/justin`, for 0.92s, with
  no `UserPromptSubmit` and no tool calls. Treat the discriminator below as
  resting on an unidentified launcher.

  To settle it, the probe needs to record the full `/proc` ancestry and each
  ancestor's `cmdline`, not just `comm` two levels up. That is work §7.2 needs
  anyway for `konsole_pid`, so it is not a detour.

## G. `tty` comes from `tty_nr`, and must be read off `claude`, not off the hook

- **Assumed:** open question 9, "reliable way to derive a session's `tty` from
  `/proc`", listed as unresolved and blocking Phase 1.
- **Observed:** field 7 of `/proc/<pid>/stat` is `tty_nr`, and decodes cleanly.
  For the live session, `tty_nr` 34817 → major 136, minor 1 → `/dev/pts/1`,
  independently confirmed by `readlink /proc/<pid>/fd/0` → `/dev/pts/1`. Two
  methods, same answer.

  ```
  major = (tty_nr >> 8) & 0xfff          # 136 == pts
  minor = (tty_nr & 0xff) | ((tty_nr >> 12) & 0xfff00)
  ```

- **The trap:** the hook's *own* process has **no controlling tty**.

  ```
  63161:python3   tty_nr=0      NO CONTROLLING TTY
  63060:bash      tty_nr=0      NO CONTROLLING TTY
   6366:claude    tty_nr=34817  /dev/pts/1
   5340:bash      tty_nr=34817  /dev/pts/1
   5256:konsole   tty_nr=0      NO CONTROLLING TTY
  ```

  A writer that reads its own `tty_nr` gets 0 every time and concludes every
  session is headless. It must read `/proc/$(os.getppid())/stat` — the `claude`
  process, per finding 3.

  Note `konsole` itself is also 0. The tty exists between `claude` and its
  shell, not above it.
- **Test:** 2026-08-15, live session, walk from a hook-spawned process to PID 1.
- **Consequence:** **open question 9 resolved.** §7.2 needs no new mechanism.

## H. The `konsole`-ancestor test for question 10 is unsound; don't build on it

- **Assumed:** finding F proposed absence of a `konsole` ancestor as the
  discriminator for a non-interactive session, replacing the `timeout`
  grandparent.
- **Observed:** it fails on nesting. Any `claude -p` launched *from* an
  interactive session inherits that session's whole chain, `konsole` included,
  and reads as interactive. Confirmed against the live chain, which contains
  `konsole` at hop 5 — anything spawned below it inherits that.
- **`tty_nr` does not rescue it either.** A headless `claude -p` typed at a
  Konsole prompt has a perfectly good controlling tty. `tty_nr` answers "which
  terminal", not "is a human driving".
- **Consequence:** withdraw the ancestry test for question 10. It stays open as
  a *detection* problem — but the requirement behind it may not need detection
  at all, see below.

### The requirement can be met without answering the question

Spec: *"Non-interactive sessions never claim a slot"* (Justin's direction,
2026-08-14). That is a statement about slots, not about detection.

Observed shapes, from 540 records:

```
e7519d22   SessionStart -> SessionEnd, 0.92s, no UserPromptSubmit, no tools
a9c23e29   SessionStart -> 16x UserPromptSubmit, 184 PreToolUse, ...
```

So: **allocate a slot on first `UserPromptSubmit`, not on `SessionStart`.** A
session nobody prompts never claims one, which is the requirement, reached
without classifying anything. `SessionStart` still creates the record — it is
needed for `starting` — it just does not take a slot yet.

This is a proposal, not a decision. It changes §6 and the `starting` state's
meaning, so it needs Justin's ruling before Phase 1 builds on it.

## F. The probe now records full `/proc` ancestry, which hands §7.2 `konsole_pid`

- **Assumed:** spec §7.2 treats finding `konsole_pid` as a walk to be written in
  Phase 3, separate from the writer's own process handling.
- **Observed:** the walk is one field on the record already being written, and
  it reaches Konsole in five hops:

  ```
  60064:python3/59963:bash/6366:claude/5340:bash/5256:konsole/2293:systemd/1:systemd
  ```

  `claude` sits at hop 3, its Konsole shell at hop 4, `konsole` itself at hop 5.
- **Test:** 2026-08-15, `probe.sh` invoked directly with a synthetic payload.
- **Consequence:** `konsole_pid` needs no separate mechanism — the writer records
  the chain and the evaluator reads it. It also gives open question 10 a real
  discriminator: **absence of a `konsole` ancestor**, rather than the presence of
  a `timeout` one, which only ever detected one particular launcher.

  The walk records each ancestor's `comm` and deliberately **not** its `cmdline`.
  A cmdline would name the launcher outright, but an ancestor of the form
  `timeout 120 claude -p "<prompt>"` puts prompt text back into the capture
  through the side door, which §4.2 forbids.

  Capture is now mode 0600, set by `umask 077` in the probe and applied to the
  existing file. It was 0644. The file holds the `cwd` of every session on the
  machine, and spec §5 requires the real state file be 0600 — a probe leaking
  what the writer protects argues against its own project.

## E2. `Stop` and `Notification` do fire; the earlier "never fired" list was young

- **Assumed:** from the first capture, `Stop` was listed among planned events
  that never fired.
- **Observed:** with 540 records rather than 51, `Stop` has fired 15 times and
  `Notification` 12. The earlier absence was a short window, not a real gap.
- **Consequence:** `waiting-input` from `Stop` (§4.4) is confirmed reachable.
  Three planned events remain genuinely unobserved — `PermissionRequest`,
  `Elicitation` and `StopFailure` — and all three need a scenario only a human
  can trigger. Treat any "never fired" list as provisional until the capture has
  covered a working session end to end.

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
