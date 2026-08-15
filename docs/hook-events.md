# Observed hook events

Phase 0 output. What Claude Code's hooks actually emit, as against what the
specification assumes.

**Status: partially gathered, 2026-08-16.** The probe is registered and live.
Eight of the ten planned events have been observed in the wild, across 621
records and six sessions; `Elicitation` and `StopFailure` are the two remaining,
and both need a scenario that has not occurred.

Raw capture is `~/.local/state/claude-state-panel/hook-probe.jsonl`, which does
survive a reboot — verified across the 2026-08-15 17:54 crash. It was
`/tmp/claude-hook-probe.jsonl` until 2026-08-15, when two hard crashes in half an
hour wiped it twice; see finding I. Everything below is the distilled record.

## Which payload fields are actually populated

Probe-captured fields per event, from 27 records across two concurrent
sessions. `cwd`, `session_id` and `hook_event_name` were present on every
single record, confirming spec §4.1.

| Event | Populated beyond the universal three |
|---|---|
| `UserPromptSubmit` | *(none captured — `prompt` exists but is deliberately not recorded)* |
| `PreToolUse` | `tool_name` |
| `PostToolUse` | `tool_name` |
| `PostToolBatch` | *(none)* |
| `Stop` | `stop_hook_active` |
| `Notification` | *(none captured — `message` exists but is not recorded)* |
| `PermissionRequest` | `tool_name` |
| `SessionStart` | `source` — always `"startup"`, see finding E |
| `SessionEnd` | `reason` — `"other"` on both observed exits |

**`matcher` is never present in the payload.** It was null on every record,
including `Notification`, where the spec assumed it could be read. See finding C
— this changes how `error_kind` must be captured.

## Observed sequences

Per tool call, invariably:

```
PreToolUse (tool_name) → PostToolUse (tool_name) → PostToolBatch
```

`PostToolBatch` fires even for a lone tool call with no siblings in the batch.

Per turn:

```
UserPromptSubmit → [tool sequences] → Stop
```

Idle, after a turn ends:

```
Stop  18:36:32
      … 60s …
Notification  18:37:32
```

Exactly 60 seconds, matching the spec's stated `idle_prompt` latency and
confirming that `Stop` is the better signal for `waiting-input`. Registering
`Notification` for that state would add a minute of delay for nothing.

Holds across 13 of 15 `Notification` records, all at 60.1s. The other two are
not idle prompts — one follows a permission prompt by 6s, one is a bare repeat
18 minutes into an idle period. `Notification` is a level, not an edge; see
finding L.

A question put to the user, `AskUserQuestion`:

```
PreToolUse (AskUserQuestion)   10:31:07
PermissionRequest             10:31:07   same instant, same tool_name
Notification                  10:31:13   +6s
      … 3m17s of human …
PostToolUse (AskUserQuestion) 10:34:24
PostToolBatch                 10:34:24
```

`PostToolUse` waits for the answer, which is what makes `waiting-answer`
implementable. `PermissionRequest` adds nothing `PreToolUse` has not already
said, and did not fire for the allowlisted `Bash` calls either side. Finding 1.

An Esc interrupt, mid-turn:

```
PostToolBatch     10:45:54
      … 380.2s, nothing whatsoever …
UserPromptSubmit  10:52:15   (the human resuming, not the interrupt)
```

No `Stop`, no `Notification`, no terminal event of any kind. The same session
had emitted both a `Notification` and a `Stop` minutes earlier, so the hooks
were live — the silence is real. This is why the staleness ceiling is the whole
mechanism for interrupts rather than a safety net; see finding 2 & 4.

A non-interactive session, in full:

```
SessionStart (source=startup)  →  SessionEnd (reason=other)
```

0.95s, no `UserPromptSubmit`, no tool calls, despite being a `claude -p "x"`
with a prompt in its argv. Launcher identified in finding K.

## Concurrency, observed

Two Claude Code sessions ran simultaneously during capture, in
`~/Code/Projects/Claude-State-Panel` and `~/Code/tana/Clautana`. Both wrote to
the same probe file without interleaving corruption. This is the product's core
case and it is real today, not hypothetical.

**Three** ran simultaneously on 2026-08-15 — this repo, `Sentry-MCP` and
`Glyph-Hunter` — and all three were killed by the same crash without a
`SessionEnd` between them. 621 records, no corruption. Finding I.

## Scenarios still to record

- [x] `SessionStart` — `source` observed, always `"startup"` (finding E)
- [x] `SessionEnd` — observed, `reason: "other"`
- [x] `PermissionRequest` — observed, carries `tool_name` (finding 1)
- [x] An `AskUserQuestion` tool call — open question 1 resolved (finding 1)
- [x] A non-interactive session — observed twice; it is a Plasma widget, not a
      scheduled run (finding K)
- [x] An Esc interrupt — observed twice on 2026-08-16, both between tool calls
      and mid-tool. Questions 2 and 4 resolved: **nothing fires at all**
      (finding 2 & 4)
- [ ] `Elicitation`
- [ ] `StopFailure`, and how `error_kind` can be obtained (see finding C)

Neither remaining item blocks Phase 1.

## Twenty documented events are not registered

The spec planned for eleven. The documented set is thirty-one. `MessageDisplay`,
`PostToolUseFailure` and `PreCompact`/`PostCompact` all bear on this design, and
`PostToolUseFailure` closes a real hole in the transition table. See finding M.

An interrupt event is **not** among the missing twenty — none exists. `Stop` is
documented not to run on user interrupt, and the feature request for one is open
and unanswered.

## Registration currently in place

**Fifteen events**, all exec form with `"args": []`, pointing at `probe/probe.sh`
in the repo checkout. The pre-existing `notify-send` handler on `Notification`
was preserved and now sits alongside the probe.

Added 2026-08-16: `PostToolUseFailure`, `PermissionDenied`, `PreCompact`,
`PostCompact`. `MessageDisplay` was deliberately not added — see finding M.

A failed tool call, verified against a deliberately failing command:

```
PreToolUse          Bash   11:23:36
PostToolUseFailure  Bash   11:23:38   <- PostToolUse does NOT fire
PostToolBatch              11:23:38
```

**The probe is installed *instead of* the writer.** Delete these registrations
before Phase 1 registers the real writer, or both will run.
