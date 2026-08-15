#!/bin/bash
# Phase 0 probe. Disposable, and installed *instead of* the writer.
#
# Records event shape only. It deliberately does not capture prompt text or
# tool_input: UserPromptSubmit carries the prompt, PreToolUse carries full tool
# arguments including file contents and shell commands. Neither is written here,
# and neither may ever be written by the real writer.
#
# For the same reason the ancestry walk records each ancestor's `comm` and never
# its cmdline. A cmdline would answer "what launched this" more directly, but an
# ancestor of the form `timeout 120 claude -p "<prompt>"` puts the prompt back in
# the capture through the side door.
#
# Answers, from its own process context:
#   - is $PPID the claude process in exec form?   (open question 3, resolved)
#   - which events actually fire, and in what order?
#   - what launched a session with no human at it?  (open question 10)
#   - how far up is the Konsole process?           (spec 7.2, konsole_pid)
#
# Output is mode 0600. The capture holds the cwd of every session on this
# machine, and spec 5 requires the real state file be 0600; a probe that leaks
# what the writer protects would be arguing against its own project.
#
# Exits 0 unconditionally. A probe must never block or annotate a tool call.

set -u
umask 077

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

# Full chain from the hook's parent up to PID 1, as pid:comm/pid:comm/...
# Bounded at 24 hops so a /proc anomaly cannot spin a hook.
ANCESTRY=""
walk_pid="$PPID"
hops=0
while [ -n "$walk_pid" ] && [ "$walk_pid" != "0" ] && [ "$hops" -lt 24 ]; do
    walk_comm=$(read_comm "$walk_pid")
    [ -z "$walk_comm" ] && break
    ANCESTRY="${ANCESTRY}${ANCESTRY:+/}${walk_pid}:${walk_comm}"
    [ "$walk_pid" = "1" ] && break
    walk_pid=$(parent_of "$walk_pid")
    hops=$((hops + 1))
done

jq -c \
    --arg ppid "$PPID" \
    --arg ppid_comm "${PPID_COMM:-unknown}" \
    --arg gpid "${GPID:-0}" \
    --arg gpid_comm "${GPID_COMM:-unknown}" \
    --arg ancestry "${ANCESTRY:-unknown}" \
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
        gpid_comm: $gpid_comm,
        ancestry: $ancestry
    }' >> "$OUT" 2>/dev/null || true

exit 0
