#!/bin/bash
# Phase 0 probe. Disposable, and installed *instead of* the writer.
#
# Records event shape only. It deliberately does not capture prompt text or
# tool_input: UserPromptSubmit carries the prompt, PreToolUse carries full tool
# arguments including file contents and shell commands. Neither is written here,
# and neither may ever be written by the real writer.
#
# Answers, from its own process context:
#   - is $PPID the claude process in exec form?   (open question 3)
#   - which events actually fire, and in what order?
#
# Exits 0 unconditionally. A probe must never block or annotate a tool call.

set -u

OUT="${CLAUDE_PROBE_OUT:-/tmp/claude-hook-probe.jsonl}"

read_comm() {
    # $1 = pid. Empty string if unreadable.
    cat "/proc/$1/comm" 2>/dev/null || true
}

parent_of() {
    # $1 = pid. Field 4 of /proc/<pid>/stat is ppid, but comm sits in
    # parentheses and may itself contain spaces, so strip up to the final ')'
    # first. After that, $1 is state and $2 is ppid.
    sed 's/.*) //' "/proc/$1/stat" 2>/dev/null | awk '{print $2}'
}

PPID_COMM=$(read_comm "$PPID")
GPID=$(parent_of "$PPID")
GPID_COMM=$(read_comm "${GPID:-0}")

jq -c \
    --arg ppid "$PPID" \
    --arg ppid_comm "${PPID_COMM:-unknown}" \
    --arg gpid "${GPID:-0}" \
    --arg gpid_comm "${GPID_COMM:-unknown}" \
    '{
        t: now,
        event: .hook_event_name,
        tool: .tool_name,
        matcher: .matcher,
        source: .source,
        reason: .reason,
        stop_hook_active: .stop_hook_active,
        sid: (.session_id // "" | .[0:8]),
        cwd: .cwd,
        hook_ppid: $ppid,
        ppid_comm: $ppid_comm,
        hook_gpid: $gpid,
        gpid_comm: $gpid_comm
    }' >> "$OUT" 2>/dev/null || true

exit 0
