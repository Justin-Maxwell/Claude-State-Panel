#!/usr/bin/env python3
"""Summarise Phase 0 probe output.

Reads the JSONL written by probe.sh and answers the questions Phase 0 exists to
answer. Standard library only, same constraint as the writer it precedes.

    probe/analyse.py [path]            summary across all sessions
    probe/analyse.py [path] --sid ab12 event sequence for one session
"""

import argparse
import collections
import json
import os
import pathlib
import sys
import time

# Spec 4.4. Every event the writer intends to register.
PLANNED = [
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "PostToolBatch",
    "PermissionRequest",
    "Elicitation",
    "Stop",
    "StopFailure",
    "SessionEnd",
]

DEFAULT_PATH = os.path.join(
    os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"),
    "claude-state-panel", "hook-probe.jsonl",
)


def load(path):
    records = []
    for lineno, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            print(f"warning: line {lineno} is not valid JSON: {exc}", file=sys.stderr)
    records.sort(key=lambda r: r.get("t", 0))
    return records


def fmt_time(epoch):
    """Local time, and the raw epoch alongside it. Never one without the other."""
    return f"{time.strftime('%H:%M:%S', time.localtime(epoch))} ({epoch:.3f})"


def summarise(records):
    print(f"records: {len(records)}")
    if not records:
        return

    first, last = records[0]["t"], records[-1]["t"]
    print(f"window: {fmt_time(first)} .. {fmt_time(last)}")
    print(f"timezone: {time.tzname[0]}")

    print("\nevents observed")
    counts = collections.Counter(r.get("event") for r in records)
    for event, n in counts.most_common():
        planned = "" if event in PLANNED else "   <- not in the writer's plan"
        print(f"  {n:5d}  {event}{planned}")

    missing = [e for e in PLANNED if e not in counts]
    print("\nplanned events that never fired")
    if missing:
        for event in missing:
            print(f"  {event}")
        print("  (an event that never fires cannot drive a state)")
    else:
        print("  none - every planned event was observed")

    print("\ntools seen on PreToolUse")
    tools = collections.Counter(
        r.get("tool") for r in records
        if r.get("event") == "PreToolUse" and r.get("tool")
    )
    for tool, n in tools.most_common():
        flag = "   <- open question 1, resolved: see finding 1" \
            if tool == "AskUserQuestion" else ""
        print(f"  {n:5d}  {tool}{flag}")
    if not tools:
        print("  none")

    print("\nmatchers seen")
    matchers = collections.Counter(
        (r.get("event"), r.get("matcher")) for r in records if r.get("matcher")
    )
    for (event, matcher), n in matchers.most_common():
        print(f"  {n:5d}  {event} / {matcher}")
    if not matchers:
        print("  none")

    print("\nprocess identity (open question 3)")
    parents = collections.Counter(
        (r.get("ppid_comm"), r.get("gpid_comm")) for r in records
    )
    for (pcomm, gcomm), n in parents.most_common():
        verdict = "getppid IS the claude process" if pcomm == "claude" else \
                  f"getppid is {pcomm!r}, NOT claude - a /proc walk is required"
        print(f"  {n:5d}  ppid={pcomm!r} gpid={gcomm!r}   {verdict}")

    print("\nsessions")
    sessions = collections.Counter(r.get("sid") for r in records)
    for sid, n in sessions.most_common():
        print(f"  {sid}  {n} events")


def sequence(records, sid):
    rows = [r for r in records if r.get("sid", "").startswith(sid)]
    if not rows:
        print(f"no records for session {sid!r}")
        return

    print(f"session {sid}, {len(rows)} events\n")
    print(f"{'time':>21}  {'gap':>8}  event")
    previous = None
    for record in rows:
        gap = "" if previous is None else f"{record['t'] - previous:7.2f}s"
        detail = record.get("tool") or record.get("matcher") or ""
        print(f"{fmt_time(record['t']):>21}  {gap:>8}  {record.get('event')} {detail}".rstrip())
        previous = record["t"]

    # A trailing transient state with no terminal event. This used to be read as
    # evidence for open question 2 -- "if this followed an Esc interrupt, nothing
    # fires". Finding I withdraws that reading: three host crashes have now
    # truncated five sessions exactly this way, and a crash is not an interrupt.
    # The shapes are indistinguishable from the record alone, so the tool states
    # what it saw and refuses to name a cause.
    tail = rows[-1].get("event")
    if tail not in ("SessionEnd",):
        idle = time.time() - rows[-1]["t"]
        print(f"\nends on {tail} with no terminal event, {idle:.0f}s ago")
        print("cause is NOT readable from this: an Esc interrupt (question 2), a")
        print("host crash (finding I), and a still-live session all look like this.")
        print("check liveness of the claude pid against boot_id before concluding.")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", nargs="?", default=DEFAULT_PATH)
    parser.add_argument("--sid", help="show the event sequence for one session")
    args = parser.parse_args()

    path = pathlib.Path(args.path)
    if not path.exists():
        print(f"no probe output at {path}", file=sys.stderr)
        return 1

    records = load(path)
    if args.sid:
        sequence(records, args.sid)
    else:
        summarise(records)
    return 0


if __name__ == "__main__":
    sys.exit(main())
