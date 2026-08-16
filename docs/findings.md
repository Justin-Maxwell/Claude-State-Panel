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

**Every Phase 1 blocker is resolved. Phase 1 is unblocked as of 2026-08-16.**

Seven resolved: 1, 2, 3, 4, 9, 7.2's `konsole_pid` as a side effect, and **10,
which was dissolved rather than answered** — see the ruling in finding H. Four
outstanding, none of which block Phase 1.

| # | Question | Phase | State |
|---|---|---|---|
| 5 | Correct Plasma 6 QML import and API for the executable data engine | 2 | not started |
| 6 | Konsole D-Bus object paths, interfaces, and the PID field matching a tab | 3 | not started |
| 7 | Can a non-focused process raise a Konsole window under KWin on Wayland? | 3 | not started |
| 8 | Does Konsole honour an OSC title sequence given the tab-title format? | 3 | not started |

Two hook events remain unobserved — `Elicitation` and `StopFailure` — but
neither was ever a blocker. `StopFailure` gates Phase 4 rendering only, and
finding C already established how `error_kind` must reach it.

Phase 2 must not begin with any Phase 0 item unresolved.

## Resolved

## N. `claude agents --json` already reports interactive session state, first-party

- **Assumed:** the whole architecture. §4 exists because Claude Code was
  believed to expose no queryable session state — issue
  [#43058](https://github.com/anthropics/claude-code/issues/43058) says exactly
  that ("no `claude --session-status` command, no state file, no Unix socket
  API") and was **closed as not planned**. Hence the writer, the state file, the
  slot bookkeeping and fifteen hook registrations: all of it infers from event
  edges what nothing would tell us directly.
- **Observed:** that is no longer true. `claude agents --json` (AgentView,
  research preview, Claude Code ≥2.1.140; this machine runs **2.1.233**) lists
  **interactive** sessions, not merely backgrounded ones:

  ```json
  {"pid": 14751, "cwd": "/home/justin/Code/Projects/Claude-State-Panel",
   "kind": "interactive", "startedAt": 1786833291511,
   "sessionId": "69e86564-...", "name": "claude-state-panel-97",
   "status": "busy"}
  ```

  The published documentation states AgentView does *not* discover interactive
  sessions in other terminals. **On this version it does.** Trust the
  observation, not the doc page.
- **Test:** 300 samples at 3s across 15 minutes, four concurrent sessions,
  correlated against the probe capture. `status` took three values —
  `idle`, `busy`, `waiting` — and a `waitingFor` field appeared alongside the
  third.
- **The correlation that matters.** A `PermissionRequest` hook fired at
  12:21:01; AgentView reported `status: "waiting"`,
  `waitingFor: "permission prompt"` at **12:21:04**, and held it for the 14
  minutes the session sat genuinely blocked. The probe recorded **zero** events
  for that session across the same window, confirming it really was blocked
  rather than the report being stale. Latency hook→CLI is ~3s.
- **Date:** 2026-08-16
- **Consequence: this is a candidate replacement for the entire Phase 1
  design**, and it is Justin's call, not mine.

  What the CLI hands over for free, that §4–§6 were going to compute:

  | Needed | Hook-derived plan | `claude agents --json` |
  |---|---|---|
  | which sessions exist | `SessionStart`/`SessionEnd` + liveness reap | the array |
  | `claude_pid` | `os.getppid()`, finding 3 | `pid` |
  | `cwd` | payload field | `cwd` |
  | interactive or not | open question 10, three findings, unsolved | `kind` |
  | working / idle | transition table | `status` |
  | blocked on the user | `PreToolUse`+`Stop` inference | `status`+`waitingFor` |
  | label | derived from `cwd`, collision-disambiguated | `name` |

  It reports *state*, not edges, which dissolves three findings at a stroke:

  - **Finding I (crash reaping)** — a dead session leaves the roster. No
    `boot_id`, no `starttime`, no PID-reuse reasoning.
  - **Finding 2 & 4 (interrupts)** — nothing to freeze, because nothing is
    inferred from a missing event. No staleness ceiling to tune.
  - **The escaped-question hole** — the state simply reverts. This was recorded
    as the widget's weakest claim and it may not exist at all under this design.

  **Costs, stated honestly.** It is a *research preview* on a version flag and
  could change or vanish — the hook contract is far more stable. It costs a
  process spawn per poll where hooks cost one write per edge. It adds ~3s of
  latency plus up to one poll interval, against sub-second for a hook. And it
  makes the widget depend on a Claude Code feature rather than on documented
  hooks.

  **Unverified, and it decides how complete the replacement is:** only
  `waitingFor: "permission prompt"` has been observed. Whether an
  `AskUserQuestion` yields a distinct value (the docs suggest `input needed`)
  is untested, and §6 wants `waiting-answer` and `waiting-permission` rendered
  differently. A second sampling run is in flight against exactly that.

## O. Prior art: one Plasma widget does share this purpose, and it is three weeks old

- **Assumed:** the README's premise, that the Claude-related Plasma widgets on
  this machine are quota widgets and nothing occupies the session-state niche.
  Justin asked for this to be re-verified before Phase 1.
- **Observed:** the quota claim holds, and the niche claim no longer does.

  **Every Claude Plasma *widget* found is a quota/usage widget** — none shows
  session state: [claude-usage-widget](https://github.com/CraigBorrows/claude-usage-widget),
  [plasma-claude-usage](https://github.com/izll/plasma-claude-usage),
  [DdeDamian/claude-quota-widget](https://github.com/DdeDamian/claude-quota-widget),
  [fuziontech/claude-quota-widget](https://github.com/fuziontech/claude-quota-widget),
  [sizeak/claude-plasma-widget](https://github.com/sizeak/claude-plasma-widget),
  [claude-usage-bar](https://github.com/Blimp-Labs/claude-usage-bar/pull/17),
  and KDE Store [Claude Usage](https://store.kde.org/p/2331316) /
  [AI Usage Monitor](https://store.kde.org/p/2353976). `plasmallm` is a chat
  widget. `Claude-KDE-Plasma-Plugin` runs the opposite direction — it lets
  Claude Code drive KDE.

  **But [AgentDiode](https://discuss.kde.org/t/agentdiode-a-local-ai-coding-agent-status-indicator-for-kde-plasma/48991)
  (announced 2026-07-28, [emreartz/AgentDiode](https://github.com/emreartz/AgentDiode))
  shares this project's purpose**: a local KDE Plasma status indicator for AI
  coding agents, showing which is working, waiting for input, or idle. Its
  privacy stance is near-identical — no prompts, code, transcripts, API keys, or
  telemetry.
- **Date:** 2026-08-16
- **Consequence:** the niche is occupied but not closed, and the differences are
  real rather than face-saving:

  | | AgentDiode | this project |
  |---|---|---|
  | form | standalone tray app, PySide6 + systemd user services | Plasma panel plasmoid, QML |
  | agents | Claude Code, Codex, Antigravity, custom | Claude Code only |
  | transport | hooks → Unix socket → daemon | hooks → state file (or finding N) |
  | maturity | **4 commits, 0 stars, 2 forks** | Phase 0 |
  | states | 7, incl. stale/disconnected on a configurable timeout | 6 planned |

  It is a *tray* indicator, not a panel widget, and it is embryonic. More to the
  point it shares this project's blind spot rather than solving it: its own
  README concedes that for some agents there is *"no dedicated event for every
  situation where a turn is waiting for a user answer"*, which is finding 2 & 4
  arrived at independently. Nothing suggests it uses `claude agents --json`
  (finding N), which is the one thing that would fix it.

  **Justin's call, and it is a real one.** Adopting or contributing to
  AgentDiode is a legitimate alternative to Phase 1. Against that: it is a
  different shape (tray vs panel), carries four agents' worth of abstraction for
  a one-agent need, and has four commits behind it.

### Prior art outside KDE, which is where the design lessons are

The idea is well-trodden on other bars, and two are worth reading before Phase 2:

- [claude-waybar-status](https://github.com/Glicio/claude-waybar-status) is the
  closest analogue to the planned design — hook-driven, state in
  `$XDG_RUNTIME_DIR/claude-state.json` under `flock`, **two sticky slots**,
  eviction of a slot-holder idle >15 min (`IDLE_THRESHOLD_SECS = 900`). Its
  documented weakness is precisely finding I: *no explicit cleanup mechanism for
  orphaned sessions; sessions without terminal events may persist indefinitely.*
  Independent confirmation that the crash case is real and is routinely missed.
- [gmr/claude-status](https://github.com/gmr/claude-status) (macOS) validates
  sessions by **checking the process is still alive** and **walks the process
  tree** to classify terminal vs IDE vs tmux — findings I and F/H, reached
  independently. It also carries a `Compacting` state, which is why
  `PreCompact`/`PostCompact` were registered in finding M.

Also: [tmux-agent-indicator](https://github.com/accessd/tmux-agent-indicator),
[tmux-agent-status](https://github.com/samleeney/tmux-agent-status),
[cc-status-bar](https://github.com/usedhonda/cc-status-bar),
[m1ckc3s/claude-status-bar](https://github.com/m1ckc3s/claude-status-bar),
[claude-sessions-monitor](https://github.com/yepzdk/claude-sessions-monitor),
and [ClaudeMon](https://claudemon.com/). The convergent design across all of
them — hook-driven, per-session slots, a state file, staleness timeouts — is
evidence the spec's architecture is the obvious one, and finding N is evidence
it may now be the obsolete one.

## M. No interrupt hook exists by design, and we are registered on 11 of 31 events

- **Assumed:** finding 2 & 4 established empirically that an Esc interrupt fires
  nothing, from a single session on one machine. That is thin evidence for a
  permanent architectural decision — a local misconfiguration or a version quirk
  would look identical.
- **Observed:** it is documented behaviour, not an accident. The `Stop` hook's
  own documentation states it *"Does not run if the stoppage occurred due to a
  user interrupt."* Independently,
  [anthropics/claude-code#9516](https://github.com/anthropics/claude-code/issues/9516)
  requests a `UserInterrupt` event, is **open with no maintainer response**, and
  dismisses timeout-based detection as unreliable — the same workaround this
  project independently arrived at.
- **Date:** 2026-08-16
- **Consequence:** stop looking for an interrupt event. The measurement and the
  documentation agree, so finding 2 & 4 rests on two independent legs and the
  staleness ceiling is not a stopgap awaiting a better event.

### The larger miss: the spec planned for 11 events; there are 31

Registered: `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`,
`PostToolBatch`, `PermissionRequest`, `Elicitation`, `Stop`, `StopFailure`,
`SessionEnd`, `Notification`. **Twenty documented events are unregistered**, and
three bear directly on this design:

| Event | Why it matters |
|---|---|
| `PostToolUseFailure` | fires after a tool call **fails** — we registered only the success event |
| `MessageDisplay` | fires *while assistant text is displayed*; a heartbeat during thinking, not just at tool boundaries |
| `PreCompact` / `PostCompact` | compaction may present as a long silence and read as false-stale |

`PostToolUseFailure` was registered and **tested against a deliberately failing
command** the same day. The result corrects a claim made earlier in this finding:

```
11:23:36  PreToolUse          Bash
11:23:38  PostToolUseFailure  Bash     <- fires
11:23:38  PostToolBatch                <- still fires, +0.1s
```

`PostToolUse` does **not** fire for a failed call, which is what the planned
transition table assumed, and it explains part of the 354-vs-348 `PreToolUse`/
`PostToolUse` deficit in the capture. But `PostToolBatch` fires regardless, so
the record moves to `thinking` a tenth of a second later. **This is a fidelity
gap, not the state-machine hole it was first described as** — no session gets
stuck. Registering it remains correct: it distinguishes a failed call from a
successful one, which §4.4's `error` rendering will want in Phase 4, and it
keeps the writer honest about what it observed.

`MessageDisplay` is the more interesting one. The ceiling of finding 2 & 4 has
to sit at ≥180s only because a working session can go 117s without emitting
anything. A heartbeat during text output would collapse that window to seconds
and sharpen `working` against `interrupted` — and if it fires for Claude Code's
own `[Request interrupted by user]` notice, it *is* the missing interrupt
signal.

**Registered 2026-08-16:** `PostToolUseFailure`, `PermissionDenied`,
`PreCompact`, `PostCompact` — all low-frequency, all pointing at the same
`probe.sh`. Fifteen events now registered. Back them out by deleting those four
keys from `~/.claude/settings.json`.

**`MessageDisplay` deliberately left off.** It may fire per text chunk, and every
hook registration is a process spawn. A spawn-per-chunk handler on a machine
already suffering hardware crashes (see finding I) is worth measuring under
control rather than switching on and hoping — and the measurement itself is the
hazard, since a per-token rate would spawn hundreds of processes before it could
be observed and reverted. Worth doing, but as a deliberate experiment with a
short-lived throwaway handler, not by adding it to the live probe.

- **Assumed:** open questions 2 and 4, the last two Phase 1 blockers. §5.3 hoped
  `Notification`/`idle_prompt` might serve as an interrupt backstop, giving the
  panel *some* event to react to when a turn is abandoned.
- **Observed:** nothing fires. Justin pressed Esc mid-turn in session
  `69e86564` on 2026-08-16 and left it. The session's last event before the
  interrupt was `PostToolBatch` at 10:45:54; the next record of any kind is his
  resuming `UserPromptSubmit` at 10:52:15.

  ```
  10:45:54  PostToolBatch
              … 380.2 seconds, no records of any kind …
  10:52:15  UserPromptSubmit
  ```

  No `Stop`. No `Notification`. The 60s `idle_prompt` of finding D would have
  landed at ~10:46:54 and did not.
- **Control — this is what makes the absence mean anything.** Both hooks are
  demonstrably live *in this same session*: it emitted `Notification` at
  10:42:21 and `Stop` at 10:43:59, minutes before the interrupt. The silence is
  a real absence, not an unregistered hook.
- **Test:** unstaged, in the session that was writing this file. 380s is six
  times the `idle_prompt` latency, so the window is not marginal.
- **The mid-tool sub-case, answered the same day.** The first observation landed
  *between* tool calls, leaving open whether a tool killed mid-flight still
  reports completion. It does not. Justin let an `AskUserQuestion` sit, then
  escaped it:

  ```
  11:01:45  PreToolUse         AskUserQuestion
  11:01:45  PermissionRequest  AskUserQuestion
  11:01:51  Notification                        (+6.0s)
              … 1073.6 seconds, nothing whatsoever …
  11:19:45  UserPromptSubmit
  ```

  **No `PostToolUse`, no `PostToolBatch`, no `Stop`.** An interrupted tool call
  emits nothing, so the record stays on `PreToolUse` indefinitely. Both interrupt
  shapes are now observed and both freeze the record; only *which* transient
  state it freezes in differs.
- **Date:** 2026-08-16
- **Consequence — this is the finding that decides how §5.3 is built.**

  **1. Question 4 is answered no.** `Notification` is not an interrupt backstop
  and there is nothing to register for one. Its only two observed roles remain
  the 60s idle prompt (finding D) and permission prompts (finding L).

  **2. An interrupted session freezes in a transient state.** Its record says
  `thinking` — or `working`, in the mid-tool sub-case — and nothing will ever
  move it. The panel would show that session **busy while it is in fact waiting
  for Justin**, which is precisely the inversion the product exists to prevent.

  **3. Crash and interrupt need different mechanisms, and now separate
  cleanly.** They were lumped together in §5.3 as "a transient state with no
  terminal event". They are not the same failure:

  ```
  host crash      process gone   -> boot_id + (pid, starttime) reap, finding I
  Esc interrupt   process alive  -> time-based staleness ceiling, the only option
  ```

  The liveness check of finding I cannot help here: the `claude` process is
  alive, healthy, and correct to be idle. **So the staleness ceiling is not a
  backstop — for interrupts it is the entire mechanism**, and it must be built
  in Phase 1 rather than deferred as a safety net.

  **4. How high the ceiling must sit, measured rather than guessed.** From 882
  gaps in which the session was *provably* still working — the gap ends in a
  further work event, not in a human typing:

  ```
  p50    0.3s     p90   15.6s     p99   56.4s     max  116.8s
  ```

  A ceiling under ~2 minutes will mark genuinely working sessions stale. **≥180s
  is the defensible floor.** Caveat: this distribution is right-censored, since
  a longer pause that happened to be interrupted is by construction excluded, so
  treat 116.8s as a lower bound on the true maximum. A long agent run or a slow
  network tool could exceed it.

  **5. What to render at the ceiling is a real question, not a detail.** The
  panel cannot distinguish "interrupted, waiting for you" from "thinking hard
  for four minutes" — the record looks identical. Recommend a distinct
  `stale`/`unknown` rendering rather than silently claiming `waiting-input`,
  since the latter would lie in the thinking-hard case. Phase 2 rendering, not a
  Phase 1 blocker.

  **6. `waiting-answer` has no ceiling that works, and this is the one state
  hook events cannot recover.** The ceiling in point 4 works for `thinking`
  because prolonged silence there is evidence of *something wrong*. It cannot
  work for `waiting-answer`, because waiting indefinitely is that state's
  correct behaviour — a real question left pending for 18 minutes while Justin
  is away is not stale, it is working exactly as intended. An escaped question
  produces a byte-identical record.

  The failure this creates is the panel's worst: a glyph reporting *"this
  session needs your answer"*, pointing at a question that no longer exists,
  indefinitely. Clicking through lands on a session asking nothing. That is
  strictly worse than showing nothing at all, because it spends the user's
  trust in the one signal the widget exists to give.

  No hook event can fix this — see finding M, which establishes that no
  interrupt event exists at any version. Two candidate escapes, neither yet
  tested:

  - `MessageDisplay` (unregistered) may fire when Claude Code displays its
    `[Request interrupted by user]` notice. If it does, it is not merely a
    heartbeat but the interrupt signal itself.
  - The session transcript under `~/.claude/projects/` records the interrupt.
    Reading it is local and credential-free, but heavier than a hook and needs
    care against §4.2, which forbids prompt text reaching the state file.

- **A caution on the earlier record.** Justin reports that some of the
  2026-08-15 crashes followed Esc interrupts. Yesterday's truncated tails may
  therefore be interrupt-then-crash rather than crash alone, and cannot be
  mined as interrupt evidence retrospectively. This is exactly why `analyse.py`
  no longer names a cause for a truncated session. This finding rests only on
  the 2026-08-16 interrupt, which was observed end to end with the process
  surviving.

## 1. `PreToolUse` fires for `AskUserQuestion`; `PostToolUse` waits for the answer

- **Assumed:** open question 1, the highest-value Phase 0 item. The spec's
  `waiting-answer` state depends on `AskUserQuestion` bracketing the human's
  thinking time — `PreToolUse` when the question is posed, `PostToolUse` only
  once it is answered. If instead `PostToolUse` fired immediately, there would be
  no event marking the wait and the state would be unreachable.
- **Observed:** confirmed, with 3m17s of human latency sitting inside the
  bracket. Session `e8356ad6`, 2026-08-16:

  ```
  10:31:07  PreToolUse         tool=AskUserQuestion
  10:31:07  PermissionRequest  tool=AskUserQuestion   (+0.0s)
  10:31:13  Notification                              (+6.0s)
  10:34:24  PostToolUse        tool=AskUserQuestion   (+3m17s)
  10:34:24  PostToolBatch
  ```

  The surrounding `Bash` calls in the same session close in ~2s, so the 3m17s is
  the human, not the tool.
- **Test:** not staged. This is an `AskUserQuestion` the assistant in an
  unrelated session (`Glyph-Hunter`) happened to ask while the probe was live,
  which is better evidence than a contrived one — nothing about the capture
  arrangement provoked it.
- **Date:** 2026-08-16
- **Consequence:** **`waiting-answer` is implementable as specified.** The
  transition is `PreToolUse` with `tool_name == "AskUserQuestion"` → enter, any
  `PostToolUse` for the same tool → leave. `tool_name` is populated on both, per
  the field table in `docs/hook-events.md`, so no matcher is needed — which
  matters, because finding C established the matcher is not readable from the
  payload.

  Two bonuses fell out of the same record:

  1. **`PermissionRequest` fires, and carries `tool_name`.** It was one of the
     three events finding E2 listed as never observed. It fired simultaneously
     with `PreToolUse` for the same tool, so it is *redundant* for
     `waiting-answer` — `PreToolUse` alone is sufficient and arrives no later.
     Note it did **not** fire for the allowlisted `Bash` calls around it, so it
     marks a decision genuinely put to the user, not every tool call.
  2. `Elicitation` and `StopFailure` remain unobserved.

## K. The `timeout`-wrapped session is a Plasma quota widget, and it never prompts

- **Assumed:** finding E recorded a 0.92s session under a `timeout` grandparent
  and stated plainly that its launcher **could not be established** — user and
  system timers, `crontab`, XDG autostart, shell profiles, `statusLine` and
  Claude Code routines were all ruled out.
- **Observed:** the ancestry field added in finding F names it. The same shape
  recurred on 2026-08-16 as session `7d0ccdb5`, 0.95s, `cwd` `/home/justin`,
  62 seconds after boot:

  ```
  4214:claude/4213:timeout/4198:bash/2836:plasmashell/2314:systemd/1:systemd
  ```

  `plasmashell` is the launcher's parent, which is why nothing in the timer or
  cron layer ever matched. The exact line is in an installed plasmoid:

  ```
  ~/.local/share/plasma/plasmoids/org.kde.plasma.claudelimits/
      contents/code/fetch_limits.sh:62

      # On first boot the token may be stale. Spawn claude briefly to trigger
      # a refresh.
      timeout 5 claude -p "x"
  ```

  Every detail matches: the `timeout` grandparent, `plasmashell`'s `cwd`, the
  sub-second lifetime against `timeout 5`, and firing ~60s after boot rather
  than on a schedule — it is a fallback taken when the widget's headers come
  back empty, which is the case immediately after boot.
- **Date:** 2026-08-16
- **Consequence:** this is the same widget the README's *Why* section cites for
  consuming quota to measure quota. It is now also the machine's only known
  producer of non-interactive Claude Code sessions, and it is **not** a
  scheduled overnight run — finding E's "scheduled" label was the assumption it
  admitted to being.

  For open question 10 this is decisive in H's favour rather than against it.
  The real-world non-interactive case, observed twice (`e7519d22`, `7d0ccdb5`),
  emits `SessionStart` → `SessionEnd` and **no `UserPromptSubmit`** — despite
  being literally a `claude -p "x"` with a prompt in its argv. So H's rule,
  *allocate a slot on first `UserPromptSubmit`*, excludes the actual case
  without classifying anything. Justin ruled for it on 2026-08-16 on exactly
  that evidence; question 10 is dissolved.

## L. `Notification` is neither unique per idle nor exclusively `idle_prompt`

- **Assumed:** finding D observed `Notification` exactly 60s after `Stop` and
  treated it as the `idle_prompt` edge.
- **Observed:** across 15 `Notification` records, 13 are 60.1s after a `Stop` —
  finding D holds, and holds tightly. The other two are not idle prompts:

  ```
  e8356ad6  10:31:13   6.0s after PermissionRequest, 1239s after the last Stop
  1932f7f5  17:27:56   1088s after the idle_prompt that already fired, still idle
  ```

  The first is the permission/question prompt's own notification. The second is
  a **repeat** — `Stop` 17:08:48, `idle_prompt` 17:09:48, then a second
  `Notification` at 17:27:56 with no intervening activity; the next
  `UserPromptSubmit` is not until 17:36:58.

  **The 6.0s permission delay is now confirmed, and the repeat is not a regular
  nag.** A second `AskUserQuestion` on 2026-08-16 reproduced the offset exactly:
  `PermissionRequest` 11:01:45 → `Notification` 11:01:51, the same 6.0s. That
  question then sat unanswered for 1073s and **no further `Notification` ever
  came**, so the 17:27:56 repeat is occasional rather than periodic. Do not
  build a timer on it.
- **Date:** 2026-08-16
- **Consequence:** `Notification` is a level, not an edge. A state machine
  driven off it would re-enter `waiting-input` on a repeat and would confuse a
  permission prompt with an idle one, since finding C established the matcher is
  not readable from the payload. **Reinforces driving `waiting-input` from
  `Stop`** (§4.4) — which is also a full minute faster.

  It does not damage `Notification`'s candidacy as the interrupt backstop (open
  question 4), but whatever consumes it there must be idempotent.

## I. A host crash ends a session with no terminal event, and takes `/tmp` with it

- **Assumed:** spec §5.3 treats a transient state with no terminal event as an
  edge case the staleness ceilings cover. The probe's own analyser frames it as
  "if this followed an Esc interrupt".
- **Observed:** it is not an edge case here. The machine hard-crashed **three
  times in 26 hours** — journal boots end at 15:36:49, 15:59:03 and 17:54:04,
  each with **no shutdown sequence, no panic trace, and the kernel log already
  silent**. Justin reports the cause as hardware. Every one took live sessions
  with it:

  ```
  a9c23e29   last record 15:23, killed by the 15:36 crash   no SessionEnd
  2314a502   last record 15:54, killed by the 15:59 crash   no SessionEnd
  1932f7f5   last record 17:52, killed by the 17:54 crash   no SessionEnd
  d980960e   last record 17:48, killed by the 17:54 crash   no SessionEnd
  94863136   last record 16:47, killed by the 17:54 crash   no SessionEnd
  ```

  `SessionEnd` does fire on an ordinary exit (finding E saw one carrying
  `reason: "other"`, and finding K a second). It cannot fire when the host dies.
  **No hook event is guaranteed to close a session record.**

  The third crash is the sharpest illustration. `1932f7f5`'s final record is a
  `Notification` — the 60s idle prompt. A panel reading the file alone would
  show that session waiting for input, correctly, and then go on showing it
  forever: three sessions, three permanently-occupied slots, on a machine that
  has since rebooted.
- **Not** an answer to open question 2. A crash and an Esc interrupt are
  different scenarios; do not read one as evidence for the other.
- **Date:** 2026-08-15, amended 2026-08-16 after the third crash
- **Consequence, two parts.**

  **1. Reap by liveness, not by event.** The panel cannot wait for a terminal
  event to free a slot. It must ask whether `claude_pid` is still alive — and
  PID reuse makes bare `/proc/<pid>` existence insufficient across a reboot,
  which is exactly when it matters. Two fields already available make the check
  exact:

  ```
  /proc/sys/kernel/random/boot_id   de5c16fa-e207-4917-82d1-d0dee7b249c9
  /proc/<pid>/stat field 22         starttime, in clock ticks since boot
  ```

  A record whose `boot_id` differs from the current one is dead by definition,
  whatever its PID now points at. Within a boot, `(pid, starttime)` identifies a
  process uniquely — a recycled PID has a later starttime. The boot_id above was
  byte-identical to journald's boot 0 ID when this was written, so the panel and
  the journal agree on what "this boot" means. Both fields cost one read; neither
  needs a walk.

  That boot_id is now `journalctl` boot **-1**; boot 0 reads
  `d82fa378-be2b-48dc-956e-333403098bd6`. The value going stale in the document
  is the mechanism working — every record written before 17:54:04 is now
  identifiable as dead by a single string comparison, with no timeout to tune and
  no ambiguity about a PID that may since have been reissued.

  The staleness ceilings stay, but as a backstop for a *hung* session, not as
  the mechanism for a dead one.

  **2. The capture moved out of `/tmp`.** It is tmpfs on this machine, so each
  crash wiped it — the 540-record base finding H reasoned from is gone, and the
  capture was down to 34 records inside a 49-second window. The three
  unresolved Phase 0 questions all need a scenario that has not happened yet,
  so the capture has to outlive the box. It is now
  `~/.local/state/claude-state-panel/hook-probe.jsonl`, mode 0600,
  `XDG_STATE_HOME`-aware, still overridable with `CLAUDE_PROBE_OUT`. The 108
  records then in `/tmp` were migrated rather than dropped.

  **Verified, 2026-08-16.** The third crash arrived before this finding was even
  committed, which tested the fix rather than the intention behind it. The
  capture read back after the reboot at 618 records, mode 0600, still holding
  every pre-crash record from the three sessions above — `/tmp/claude-hook-probe.jsonl`
  no longer exists. Findings 1, K and L are all reasoned from records that the
  old location would have destroyed.

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
- **Consequence:** withdraw the ancestry test for question 10. It was left open
  as a *detection* problem — but the requirement behind it never needed
  detection at all, and the ruling below removes the question entirely.

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

**Ruled by Justin, 2026-08-16: adopted.** A glyph appears when he first types
into a session, not when the session opens. **Open question 10 is therefore
dissolved, not answered** — the panel never asks whether a session is
interactive, so it cannot get the answer wrong. Delete any remaining plan to
detect it.

What this settles for Phase 1:

- `SessionStart` creates the record but claims no slot and renders nothing.
- The first `UserPromptSubmit` claims the slot. Subsequent ones do not.
- `SessionEnd`, or the liveness reap of finding I, releases it.
- The `starting` state survives but is **not** a rendered state; it is the
  window between `SessionStart` and the first prompt. §6 needs rewriting to say
  so.

The accepted cost, stated so Phase 2 does not treat it as a bug: a session
Justin has opened but not yet typed into shows nothing on the panel. That is
the intended behaviour — such a session is not waiting on him, and he is
looking straight at it.

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
