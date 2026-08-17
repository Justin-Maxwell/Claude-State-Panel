# Remote Control as a Monitoring Substrate — Exploration Plan

- **Status** — exploration only. No widget code. Extends the existing Phase 0 gate rather than replacing it.
- **Host** — `phenom` (Fedora, KDE Plasma 6, Wayland)
- **Consumer** — `claude-state-panel` (Plasma 6 panel widget)
- **Date** — 2026-08-17

---

## 1. Why this exists

### 1.1 The precipitating problem

- The hook layer is an unreliable source of the one signal the panel most needs: **"Claude is waiting for you."**
  - `Notification` + `idle_prompt` — the canonical "done and waiting" matcher — is reported as not firing in VS Code and unreliable in the terminal CLI. `[7%|7%|5%]`
  - `Stop` fires on **every response turn**, not only genuine completions, so it cannot be used as a drop-in substitute without deduplication.
  - Community workarounds converge on transcript-JSONL parsing and cooldown files — which is itself a signal that the *transcript*, not the hook, is the reliable substrate. `[6%|6%|4%]`

### 1.2 The existence proof

- Remote Control **does** deliver a working attention signal: push notification on long-task completion and on decision-required.
- Therefore the engine can emit a trustworthy attention event. The question is which tap point exposes it. `[5%|6%|4%]`

### 1.3 The quality bar

- Target is **not** "some indicator on the panel". Target is **at least the mobile client's monitoring quality**, locally:
  - per-session live state
  - distinguishing *working* / *blocked on permission* / *blocked on question* / *finished*
  - multiple concurrent sessions, distinguishable
  - online/offline status per session
- → See [§6 Capability parity checklist](#6-capability-parity-checklist).

---

## 2. Standing constraints

- **C1 — Phase 0 discipline holds.** Empirical probing is a hard gate. No widget code is written until the tap point is chosen and its event vocabulary is documented from observation, not from docs.
- **C2 — Do not lose the previous-turn jump.** The console CLI's top-line turn-jump affordance is now a known-good, in-hand capability. Any surface migration that discards it is a regression, regardless of what it gains. → [§7.4](#74-surface-regression-risk)
- **C3 — Read-only by default.** The panel is a *monitor*. Any tap point that requires the panel to sit in the command path is out of scope for v1.
- **C4 — Assume a hostile LAN.** Consistent with existing operating posture on this network. Bears directly on [§5.4](#54-t4--sdk-url-local-bridge).
- **C5 — No plan-gated dependency without confirmation.** Remote Control is a research preview on Pro/Max/Team/Enterprise; API keys are unsupported. Confirm entitlement before building on it. `[4%|5%|3%]`

---

## 3. Corrected architecture model

### 3.1 What Remote Control actually is

- A **bridge**, not a server.
  - Local CLI opens an **outbound** WebSocket to Anthropic: `wss://api.anthropic.com/v1/session_ingress/ws/{session_id}` `[6%|6%|4%]`
  - Remote UI (phone / `claude.ai/code`) is a *window* into the local session.
  - Execution, filesystem and MCP servers remain local; only messages and tool results traverse the bridge.
- **Implication:** there is no localhost listener to attach a widget to. The original assumption is falsified unless [§4 H1](#4-hypotheses) survives probing.

### 3.2 Documented operating modes

- Server
- Interactive Session
- Existing session (`/remote-control` inside a running session)
- Plus `enableRemoteControlForAllSessions` via `/config` — makes every session remotely reachable without explicit invocation. `[5%|6%|4%]`
- → Mode choice materially affects what a monitor can see. Probe all three.

### 3.3 On-disk residue

- JSONL transcripts carry a `slug` field; telemetry carries an `is_claude_code_remote` flag — together sufficient to distinguish local from bridged sessions. `[6%|7%|5%]`
- → This is the sleeper candidate. See [§5.1](#51-t1--jsonl-transcript-tail).

---

## 4. Hypotheses

Each stated so it can be **falsified**, not confirmed.

| # | Hypothesis | Prior | Falsifier |
|---|---|---|---|
| H1 | An RC-related process listens on localhost that a widget can read | **Low** — contradicted by outbound-bridge design | `ss -tlnp` during an active RC session shows no CC-owned listener |
| H2 | JSONL transcript tail exposes every state the mobile UI shows | Moderate–high | A state visible on the phone has no corresponding transcript record |
| H3 | RC emits attention events the hook layer drops | Moderate | Phone notification fires with no hook firing, or vice versa, under identical conditions |
| H4 | `--sdk-url` to a local server yields the full event stream | High (per reversing write-up) | Connection refused, flag removed, or plan-gated |
| H5 | Statusline mechanism already carries enough state | Unknown — untested | Statusline payload lacks blocked/waiting distinction |
| H6 | Session-level online/offline is observable locally | Unknown | No local artefact changes when the bridge drops |

---

## 5. Candidate tap points, ranked by risk

Ordering is **ascending risk**, not descending richness. Prefer the lowest-risk tap that clears [§6](#6-capability-parity-checklist).

### 5.1 T1 — JSONL transcript tail

- **Mechanism** — `inotify` watch on the session transcript directory; parse appended records.
- **Risk** — lowest. Read-only, no protocol participation, no flags, no network.
- **Unknowns**
  - Does a *pending question* appear in the transcript at the moment it blocks, or only once answered? — **critical; this single question may decide the whole plan**
  - Write latency vs. UI state change.
  - Behaviour under RC (`slug` / remote flag).
- **Verdict if it clears** — build here. Everything below becomes unnecessary.

### 5.2 T2 — Statusline mechanism

- **Mechanism** — Claude Code's own statusline configuration hook; a script receives session state and returns a rendered line.
- **Risk** — low. First-party, documented, designed to be consumed.
- **Unknowns** — payload schema; whether it distinguishes *blocked-on-permission* from *blocked-on-question* from *thinking*; update cadence.
- **Attraction** — this is the closest thing to a *sanctioned* state feed, and it is almost certainly under-explored relative to hooks.

### 5.3 T3 — Hook layer (existing Phase 0 work)

- **Mechanism** — `~/.claude/settings.json` hooks. Shared between CLI and extension, so surface-agnostic.
- **Risk** — low, but **reliability is the known defect**, not the risk.
- **Status** — already the subject of Phase 0. Do not abandon; **re-scope** it to establish the *failure envelope* rather than to build on it.
  - Which matchers fire, per surface, per mode?
  - Does RC-active change hook behaviour? ← genuinely unknown, genuinely important

### 5.4 T4 — `--sdk-url` local bridge

- **Mechanism** — launch Claude Code pointed at a local WebSocket server speaking CCR v1; server observes the full lifecycle.
- **Richness** — highest by a wide margin. `system/init`, `initialize`, prompt dispatch, streamed responses, tool-permission handling, results.
- **Risk — substantial, and not only technical**
  - **Undocumented.** No stability contract. Can vanish in any release.
  - **Characterised as an abuse vector** in published security research; defenders are advised to alert on `--sdk-url` pointing anywhere non-Anthropic. Expect this path to be narrowed. `[7%|6%|4%]`
  - **Sits in the command path.** Violates [C3](#2-standing-constraints). A server that auto-approves tool permissions is not a monitor; it is an authority.
  - **[C4](#2-standing-constraints) interaction.** On an assumed-compromised LAN, standing up a local WS endpoint that mediates an agent's tool approvals is a materially worse posture than tailing a file. Bind loopback-only, or don't do it.
- **Verdict** — **probe for knowledge, do not build on it.** Useful as ground truth against which to validate T1/T2 coverage. Not a v1 substrate.

### 5.5 T5 — Passive observation of the outbound bridge

- **Mechanism** — observe that the WS to `api.anthropic.com` exists / is healthy, without reading it (TLS).
- **Yield** — connection liveness only. Maps to online/offline dot, nothing more.
- **Verdict** — cheap supplement to T1/T2; never a primary.

---

## 6. Capability parity checklist

The bar from [§1.3](#13-the-quality-bar). Each tap point is scored against it.

- [ ] Session enumerated, named, distinguishable
- [ ] State: idle
- [ ] State: thinking / working
- [ ] State: blocked — permission request
- [ ] State: blocked — question to user *(distinct from permission)*
- [ ] State: finished this turn
- [ ] State: finished and idle *(the signal hooks lose)*
- [ ] Error / crashed
- [ ] Bridge online/offline
- [ ] Multi-session concurrent, no cross-talk
- [ ] Latency acceptable for a panel (target: sub-second perceived)
- [ ] Survives session resume
- [ ] Survives machine sleep/wake

---

## 7. Probe sequence

Run in order. Each probe is a **written observation**, not code.

### 7.1 P1 — Establish entitlement and baseline

- Confirm RC is available on the account and not org-gated.
- Start one session each in the three modes ([§3.2](#32-documented-operating-modes)).
- Record: what the terminal shows, what `claude.ai/code` shows, what the phone shows.

### 7.2 P2 — Falsify H1 before anything else

- During an active RC session: `ss -tlnp`, `lsof -p <pid>`, process tree.
- **Cheapest probe in the plan and it removes the largest assumption.** Do it first.

### 7.3 P3 — Transcript coverage matrix

- Drive one session deliberately through **every row of [§6](#6-capability-parity-checklist)**.
- For each: does a transcript record appear, when, and is it unambiguous?
- Simultaneously record hook firings and phone notifications.
- Output: a three-column truth table — *observed UI state* / *transcript record* / *hook fired*.
- This single artefact resolves H2, H3 and most of H5.

### 7.4 P4 — Statusline payload capture

- Configure a statusline script that does nothing but dump its input to a log.
- Replay the P3 drive. Diff coverage against the transcript column.

### 7.5 P5 — CCR ground truth *(optional, gated)*

- Only if P3+P4 leave gaps that matter.
- Loopback-bound local server, throwaway repo, no real credentials in scope, network egress observed.
- Purpose is **coverage validation**, not production use. → [§5.4](#54-t4--sdk-url-local-bridge)

### 7.6 P6 — Disruption behaviour

- Sleep/wake `phenom` mid-session. Drop network. Observe reconnection and whether queued updates arrive.
- Docs claim status updates from subagents and workflows are queued during rebuild and delivered on recovery — verify this locally rather than trusting it. `[5%|6%|4%]`

---

## 8. Decision gates

- **G1** — H1 falsified? → drop the localhost-listener design entirely, no fallback.
- **G2** — Does T1 alone clear [§6](#6-capability-parity-checklist)? → **build on T1. Stop exploring.**
- **G3** — T1 + T2 together clear it? → build on the pair; hooks become optional garnish.
- **G4** — Gaps remain after T1+T2+T3? → escalate to P5 *for knowledge only*, then decide whether the missing capability is worth the [§5.4](#54-t4--sdk-url-local-bridge) risk. Default answer: **no**.

---

## 9. Surface regression risk

- Per [C2](#2-standing-constraints): the previous-turn jump lives in the console CLI.
- If the panel's chosen substrate implicitly pushes work toward a GUI surface that lacks it, the panel has cost more than it delivered.
- **Mitigation** — the panel should be **surface-agnostic**. If T1/T2 hold across CLI, VS Code and desktop app equally, the console remains a first-class home and C2 is satisfied for free. Verify this explicitly in P3 by running the drive on at least two surfaces. `[5%|6%|4%]`

---

## 10. Open questions

- Does an RC-active session change hook firing behaviour? *(unknown, high value)*
- Is there a documented statusline schema, or must it be derived by observation?
- Does `enableRemoteControlForAllSessions` alter the on-disk artefacts even when no remote client connects?
- Is the mobile push notification generated locally or server-side? — **if server-side, it is not reproducible locally at all**, and the parity target must be revised downward. `[8%|7%|5%]`
- Does Dispatch (desktop app) emit anything distinguishable from an ordinary session?

---

## 11. What `claude-desktop` changes — observed 2026-08-17

Written from a live Desktop session (`4e1db5ed`, pid 27436) on `phenom`. Everything
below is **observed**, not read from docs. The install is
`claude-desktop-unofficial`, bundling Claude Code **2.1.229** at
`~/.config/Claude/claude-code/2.1.229/claude`, alongside the CLI's **2.1.233** at
`~/.local/share/claude/versions/`. Two Claude Code versions now run concurrently.

### 11.1 The panel is blind to Desktop sessions — today, silently

- `claude agents --json` **does** report the Desktop session: `kind: "interactive"`,
  correct `pid`, `cwd`, `sessionId`, `name`.
- It reports **no `status` field at all**, across three polls while the session was
  demonstrably busy. The sibling CLI session reported `status: "idle"` in the same
  poll. *(Idle-state observation outstanding — sampler running.)*
- `just doctor` therefore renders **"1 session, none waiting on you"** while two
  interactive sessions are open and one of them is this one.
- Cause: `reportable()` in `evaluator/claude-state-eval.py:129` gates on
  `session.get("status") is not None`. That gate exists to keep a headless
  `claude -p` from claiming a slot — `kind` could not do it. **A Desktop session is
  indistinguishable from a headless one under that test.**
- This is the worst possible failure mode for the stated purpose: a session with no
  terminal to glance at is exactly the one the panel exists to surface, and it is
  the one dropped without a warning.

### 11.2 The second interactivity heuristic is wrong too

- Hooks **fire normally** for the Desktop session: 36 records, `SessionStart`,
  `UserPromptSubmit`, `PreToolUse`/`PostToolUse`/`PostToolBatch`. The desktop app
  reads `~/.claude/settings.json`. T3 is surface-agnostic in the way §9 hoped.
- But the recorded `ancestry` is
  `27436:claude/13616:claude-desktop/13599:claude-desktop-/2307:systemd/1:systemd`.
- **No `konsole` ancestor.** The README's fallback discriminator — *no konsole
  ancestor ⇒ non-interactive* — misclassifies Desktop as non-interactive.
- So both independent interactivity tests in the design fail on the same new case,
  for unrelated reasons. Neither was wrong when written; the population changed.

### 11.3 T1 is strengthened — it is now the only substrate proven to cover both

- The Desktop session writes to the **same store**:
  `~/.claude/projects/<slug>/4e1db5ed-….jsonl`, `version: "2.1.229"`, `cwd` and
  `gitBranch` present.
- New record type observed that the CLI transcripts do not carry: **`queue-operation`**
  (keys `content`, `operation`, `sessionId`, `timestamp`, `type`) — the desktop
  app's prompt queue. Worth understanding: it may be an *earlier* signal than
  anything the CLI emits.
- `slug` was **absent** on every record (no RC active), so §3.3's local/bridged
  discriminator is unconfirmed and must not be assumed.
- → [§8 G2](#8-decision-gates) gains weight. T1 covers CLI, Desktop and (per §9)
  presumably VS Code from one watch.

### 11.4 H1 falsified — and a new local IPC surface appeared

- **No TCP listener** on any interface owned by any `claude` or `claude-desktop`
  process. Enumerated by inode→pid over `/proc/net/tcp{,6}`. [H1](#4-hypotheses) is
  dead; [G1](#8-decision-gates) fires. Delete the localhost-listener design.
- What exists instead is a **UNIX socket tree**: `/tmp/cc-daemon-1000/a6c727e8/`
  containing `control.sock`, `pty/<sid>.sock`, `rv/<sid>.sock`, `spare/…`.
- Owner is `claude daemon run --origin transient --spawned-by {…pid 26904}` — spawned
  by the **CLI** session, hosting its background agents. Not a Desktop artefact.
- This is a **new candidate, T6**, and it is materially safer than
  [T4](#54-t4---sdk-url-local-bridge): filesystem-scoped, unreachable from the LAN by
  construction, so [C4](#2-standing-constraints) does not bite. Still undocumented,
  still likely in the command path — so the same verdict applies: **probe for
  knowledge, do not build on it.** `[6%|6%|4%]`
- `/tmp` is tmpfs here (finding I). Runtime-only state, wiped on crash — correct for
  sockets, disqualifying for anything durable.

### 11.5 A first-party session registry exists, but not for us

- The desktop app exposes `ccd_session_mgmt` MCP tools to the *model*:
  `list_sessions`, `get_session`, `list_events`, `search_session_transcripts`.
  `get_session` is documented to return model, worktree/branch, **and whether the
  session is remote** — three §6 rows, first-party.
- `list_sessions` from this session returned **"No other sessions found"** while two
  CLI sessions and a background agent were live. It enumerates **CCD sessions only**.
- It is an MCP tool surface, not a process a widget can query. **Not a panel
  substrate.** Its value is as *ground truth* for validating T1 coverage — the role
  §5.4 wanted T4 for, at none of the risk.

### 11.6 Consequences for the plan

- **C2 sharpened.** The previous-turn jump lives in the console CLI, and Justin is
  now submitting from Desktop. The surface migration §9 treated as a risk has
  *already begun*. The panel must be surface-agnostic in fact, not in principle.
- **Phase 3 is now partial by construction.** Konsole D-Bus tab focus cannot act on
  a Desktop session. Click-to-focus needs a per-surface action, chosen from the
  ancestry chain — which §11.2 shows is already recorded.
- **Version skew is a standing hazard.** `claude agents --json` is a research-preview
  schema and there are now two versions of it on one machine. The `status`-absence in
  §11.1 may be a 2.1.229-vs-2.1.233 artefact rather than a Desktop one. **Distinguish
  these before fixing anything** — run `agents --json` from *both* binaries.
- **Do not "fix" §11.1 by dropping the `status` gate.** That would readmit headless
  `claude -p` sessions and undo the 2026-08-14 ruling. The discriminator has to move
  to something that actually separates the two — ancestry (`claude-desktop` present)
  is the obvious candidate and is already captured.

### 11.7 Probe additions

- **P7** — `agents --json` from the 2.1.229 binary and the 2.1.233 binary against the
  same session set. Isolates version skew from surface. **Do this before any code.**
- **P8** — capture one Desktop session through every row of [§6](#6-capability-parity-checklist),
  especially *blocked on permission* and *blocked on question*: does `status`/`waitingFor`
  ever appear for Desktop, or is the field absent for the whole lifecycle?
- **P9** — characterise `queue-operation` records. Latency vs. UI state change.
- **P10** — `ccd_session_mgmt.get_session` on a live session as the §6 ground-truth
  column in P3's truth table, replacing the gated [P5](#75-p5---ccr-ground-truth-optional-gated).

---

## 12. Sources

- Claude Code docs — Remote Control: `https://code.claude.com/docs/en/remote-control`
- Claude Code docs — mobile: `https://code.claude.com/docs/en/mobile`
- Claude Code docs — VS Code: `https://code.claude.com/docs/en/vs-code`
- `anthropics/claude-code` issue #29928 — completion-notification reliability
- `anthropics/claude-code` issue #57230 — VS Code native notifications
- frr.dev — Remote Control bridge API teardown (WebSocket endpoint, on-disk traces)
- Origin — CCR v1 protocol reversing (`--sdk-url`, lifecycle, security characterisation)

> Third-party reversing write-ups are **starting points for probes, not authorities**. Anything load-bearing gets confirmed on `phenom` before it enters the spec.
