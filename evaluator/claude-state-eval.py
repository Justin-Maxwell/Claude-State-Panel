#!/usr/bin/env python3
"""The evaluator: the one place where truth is computed.

Everything the panel, the popup and `doctor` display comes from `evaluate()`.
None of them recompute anything, which is what stops the panel and the CLI from
disagreeing about what a session is doing.

Source of truth is `claude agents --json` (finding N), not the hook stream the
specification originally assumed. That decision is Justin's, 2026-08-16. The
CLI reports session *state*; the hook stream reported state *transitions*, from
which state had to be inferred. Three whole classes of bug came from that
inference and none of them survive the change:

  - a host crash left a record with no terminal event      (finding I)
  - an Esc interrupt froze a record in a transient state   (finding 2 & 4)
  - an escaped AskUserQuestion claimed "needs your answer"
    permanently, and no timeout could fix it because
    waiting indefinitely is what that state is *for*       (finding 2 & 4)

A session that dies, is interrupted, or has its question dismissed simply stops
being reported that way on the next poll. There is no reaping, no staleness
ceiling, and no liveness check in this file, and their absence is the point.

Standard library only. No network. Never reads ~/.claude/.credentials.json.
"""

import json
import os
import subprocess
import time

SCHEMA = 1

# How many sessions get a glyph before the rest collapse into an overflow badge.
DEFAULT_SLOTS = 4

# The CLI's own vocabulary, mapped to ours. `status` alone is not enough: a
# blocked session reports status="waiting" and puts the reason in `waitingFor`,
# and section 6 renders "needs a decision" differently from "needs an answer".
#
# Verified 2026-08-16 across 509 samples of two blocking scenarios:
#   permission prompt -> waitingFor="permission prompt"
#   AskUserQuestion   -> waitingFor="input needed"
WAITING_FOR = {
    "permission prompt": "waiting-permission",
    "input needed": "waiting-answer",
    # Documented but not yet observed here. A sandbox request is a permission
    # decision by another name, so it renders as one rather than as unknown.
    "sandbox request": "waiting-permission",
}

# Highest priority first. This orders the panel, decides which session's glyph
# the overflow badge borrows, and decides who keeps a slot under contention.
#
# The two waiting states outrank everything because they are the only ones that
# are actually blocked on Justin. `idle` outranks `working` because an idle
# session is his turn, where a working one needs nothing from him.
PRIORITY = [
    "waiting-permission",
    "waiting-answer",
    "idle",
    "working",
    "unknown",
]

# States that mean a session is blocked and cannot proceed without Justin.
# The panel exists to answer "is anything waiting on me"; this is that set.
ATTENTION = frozenset({"waiting-permission", "waiting-answer"})

# Glyph and colour live here, not in the renderers, so the panel, the popup and
# `doctor` cannot disagree -- and so the overflow badge can borrow the
# highest-priority hidden session's appearance without recomputing it.
#
# `?` and `!` are chosen over more decorative marks because they survive being
# 16 pixels wide in a panel and still read as "answer me" and "decide".
GLYPH = {
    "waiting-permission": "!",
    "waiting-answer": "?",
    "working": "●",        # filled circle
    "idle": "○",           # hollow circle
    "unknown": "·",
}

# Colour *names*, deliberately not hex. The plasmoid maps these onto the active
# Plasma colour scheme; `doctor` maps them onto ANSI. Hard-coding hex here would
# make the widget ignore the user's theme.
#
# Provisional: Justin's direction is that working and pending-user-prompt are
# both green, so only the two blocked states carry an alerting colour. The
# specification's own colour table is not yet in this repo to check against.
COLOUR = {
    "waiting-permission": "attention",
    "waiting-answer": "attention",
    "working": "active",
    "idle": "active",
    "unknown": "neutral",
}


def classify(session):
    """Map one CLI session entry to (state, warning-or-None).

    Unrecognised input yields "unknown" plus a warning rather than a guess or a
    crash. A future Claude Code release adding a status is a display bug here,
    not an outage.
    """
    status = session.get("status")
    if status == "busy":
        return "working", None
    if status == "idle":
        return "idle", None
    if status == "waiting":
        waiting_for = session.get("waitingFor")
        state = WAITING_FOR.get(waiting_for)
        if state:
            return state, None
        # Blocked on *something* we do not have a name for. Report it as
        # needing attention rather than losing it: a wrongly-labelled blocked
        # session is far less harmful than a silently dropped one.
        return "waiting-answer", (
            f"unrecognised waitingFor {waiting_for!r}; "
            "treated as waiting-answer"
        )
    return "unknown", f"unrecognised status {status!r}"


def label_for(session):
    """Human label. The basename of cwd is what Justin recognises at a glance."""
    cwd = session.get("cwd") or ""
    return os.path.basename(cwd.rstrip("/")) or cwd or "?"


def _disambiguate(entries):
    """Give colliding labels a discriminator, and only colliding ones.

    Two sessions in different checkouts of the same project name are the case
    that matters. Everything else keeps a clean label.
    """
    counts = {}
    for entry in entries:
        counts[entry["label"]] = counts.get(entry["label"], 0) + 1
    for entry in entries:
        if counts[entry["label"]] > 1:
            parent = os.path.basename(os.path.dirname((entry["cwd"] or "").rstrip("/")))
            entry["label"] = f"{entry['label']} ({parent or entry['short_id']})"


def _local(epoch):
    """Localised string for a raw epoch. Raw value is always emitted alongside.

    Tests run under three timezones and require the raw epochs to be identical
    and only these strings to differ.
    """
    return time.strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime(epoch))


def evaluate(raw_sessions, now=None, slots=DEFAULT_SLOTS, warnings=None):
    """Pure function: CLI session list -> the model every renderer draws.

    `raw_sessions` is exactly what `claude agents --json` returns. Passing it as
    an argument rather than fetching it inside is what makes this testable with
    no live session and no Plasma shell.
    """
    now = time.time() if now is None else now
    warnings = list(warnings or [])
    entries = []

    for session in raw_sessions:
        # Non-interactive sessions never claim a slot -- Justin's direction,
        # 2026-08-14. Under the hook architecture this needed a discriminator
        # nobody could derive (open question 10, findings E/F/H). The CLI simply
        # reports `kind`, so the requirement is now one comparison.
        if session.get("kind") != "interactive":
            continue

        state, warning = classify(session)
        if warning:
            warnings.append(warning)

        started_ms = session.get("startedAt")
        started = started_ms / 1000.0 if isinstance(started_ms, (int, float)) else None
        session_id = session.get("sessionId") or ""

        entries.append({
            "session_id": session_id,
            "short_id": session_id[:8],
            "pid": session.get("pid"),
            "cwd": session.get("cwd"),
            "label": label_for(session),
            "name": session.get("name"),
            "state": state,
            "glyph": GLYPH.get(state, GLYPH["unknown"]),
            "colour": COLOUR.get(state, "neutral"),
            "attention": state in ATTENTION,
            "waiting_for": session.get("waitingFor"),
            "started_at": started,
            "started_at_local": _local(started) if started else None,
            "age_secs": round(now - started, 1) if started else None,
        })

    _disambiguate(entries)

    # Priority first, then oldest first so the order is stable between polls.
    # An order that reshuffles under the cursor is worse than a wrong one.
    rank = {state: i for i, state in enumerate(PRIORITY)}
    entries.sort(key=lambda e: (rank.get(e["state"], len(PRIORITY)),
                                e["started_at"] or 0.0,
                                e["short_id"]))

    visible, overflow = entries[:slots], entries[slots:]
    for index, entry in enumerate(visible):
        entry["slot"] = index
    for entry in overflow:
        entry["slot"] = None

    return {
        "schema": SCHEMA,
        "generated_at": now,
        "generated_at_local": _local(now),
        "source": "claude agents --json",
        "slots": slots,
        "sessions": visible,
        "overflow": {
            # The badge borrows the highest-priority hidden session's state, so
            # a hidden session needing attention still shows as needing it.
            "count": len(overflow),
            "state": overflow[0]["state"] if overflow else None,
            "glyph": overflow[0]["glyph"] if overflow else None,
            "colour": overflow[0]["colour"] if overflow else None,
            "attention": any(e["attention"] for e in overflow),
            "sessions": overflow,
        },
        "attention_count": sum(1 for e in entries if e["attention"]),
        "session_count": len(entries),
        "warnings": warnings,
    }


def fetch(argv=("claude", "agents", "--json"), timeout=15):
    """Run the CLI and parse it. Returns (sessions, warnings).

    Every failure path yields an empty list plus a warning. A panel that
    disappears is a bug report; a panel that shows a stale lie is a trap.
    """
    try:
        proc = subprocess.run(list(argv), capture_output=True, text=True,
                              timeout=timeout)
    except FileNotFoundError:
        return [], [f"{argv[0]!r} not found on PATH"]
    except subprocess.TimeoutExpired:
        return [], [f"{' '.join(argv)} timed out after {timeout}s"]
    except OSError as exc:
        return [], [f"{' '.join(argv)} failed: {exc}"]

    if proc.returncode != 0:
        detail = (proc.stderr or "").strip().splitlines()
        return [], [f"{' '.join(argv)} exited {proc.returncode}"
                    + (f": {detail[0]}" if detail else "")]
    try:
        parsed = json.loads(proc.stdout)
    except ValueError as exc:
        return [], [f"could not parse {' '.join(argv)} output: {exc}"]
    if not isinstance(parsed, list):
        return [], [f"expected a JSON array, got {type(parsed).__name__}"]
    return parsed, []


def current(slots=DEFAULT_SLOTS, now=None):
    """Fetch and evaluate in one step. The renderers' entry point."""
    sessions, warnings = fetch()
    return evaluate(sessions, now=now, slots=slots, warnings=warnings)
