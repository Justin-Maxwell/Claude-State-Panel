# Observed hook events

Phase 0 output. What Claude Code's hooks actually emit, as against what the
specification assumes.

**Status: partially gathered, 2026-08-14.** The probe is registered and live.
Four of the ten planned events have been observed in the wild; the rest need
scenarios that did not occur during the first session.

Raw capture is `/tmp/claude-hook-probe.jsonl`, which is tmpfs and **will not
survive a reboot**. Everything below is the distilled record.

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

## Concurrency, observed

Two Claude Code sessions ran simultaneously during capture, in
`~/Code/Projects/Claude-State-Panel` and `~/Code/tana/Clautana`. Both wrote to
the same probe file without interleaving corruption. This is the product's core
case and it is real today, not hypothetical.

## Scenarios still to record

- [ ] `SessionStart` — neither session was started after the probe was
      registered, so `source` has never been seen populated
- [ ] `SessionEnd`
- [ ] `PermissionRequest`
- [ ] `Elicitation`
- [ ] `StopFailure`, and how `error_kind` can be obtained (see finding C)
- [ ] An `AskUserQuestion` tool call — open question 1, the highest-value item
- [ ] An Esc interrupt, mid-thinking and mid-tool — open questions 2 and 4
- [ ] A non-interactive session, e.g. the scheduled overnight run — open
      question 10

## Registration currently in place

Ten events plus `Notification`, all exec form with `"args": []`, pointing at
`probe/probe.sh` in the repo checkout. The pre-existing `notify-send` handler on
`Notification` was preserved and now sits alongside the probe.

**The probe is installed *instead of* the writer.** Delete these registrations
before Phase 1 registers the real writer, or both will run.
