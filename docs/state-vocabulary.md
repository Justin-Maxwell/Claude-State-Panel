# State vocabulary

What a panel glyph is allowed to say, and by which channel it says it.

This is deliberately maximal. Every distinction the hook data supports is drawn
here, so the busiest possible version can be seen running before anything is
pruned. A collapse order is proposed at the end; nothing is collapsed yet.

Supersedes the glyph and colour table in spec §5. The state set, priority order
and eviction constants are unchanged.

## Principle

**Colour is never the only channel.** Every state is separable by glyph alone,
in monochrome, at panel size. Colour is a second, redundant channel that makes
scanning faster.

This is not decoration. Claude Desktop's own sidebar dots are the counter-example
— [issue #72468](https://github.com/anthropics/claude-code/issues/72468) reports
its three states are *"very close in hue/brightness and hard to tell apart at a
glance"*, and asks for exactly this: shape as well as colour, per WCAG 1.4.1.

**No hex literals.** Every colour is a Kirigami theme role, so the panel tracks
the user's colour scheme, light or dark, including the daltonised schemes. One
scoped exception, below.

## Four channels

| Channel | Carries | Vocabulary |
|---|---|---|
| Glyph | state, and its subtype where one exists | see below |
| Colour | state, as a theme role | one role per state |
| Intensity | how long the session has sat in this state | continuous ramp |
| Ordinal | which of several sessions in one project | superscript digit |

Plus a fifth, off the glyph itself: a project hue rule under the glyph. See
*Project identity*.

## States and roles

`platformtheme.h` in Kirigami exposes nine text colour roles. The previous
mapping used four across seven states, so colour largely repeated what the glyph
already said. One role per state now, and colour becomes information.

| State | Glyph | Theme role | Why that role |
|---|---|---|---|
| `error` | see *Error kinds* | `negativeTextColor` | something failed |
| `waiting-permission` | ❗ | `neutralTextColor` | a caution awaiting a decision |
| `waiting-elicitation` | ❓ | `activeTextColor` | the role meaning *needs attention* |
| `waiting-input` | ● | `positiveTextColor` | the turn ended cleanly, it is yours |
| `tool` | see *Tool classes* | `linkColor` | actively doing something |
| `thinking` | ◐ | `textColor` | ordinary running state |
| `starting` | ◌ | `disabledTextColor` | not yet live |

`stale` is no longer a colour. It is the bottom of the intensity ramp, so a
stale session keeps its own state colour and glyph rather than collapsing into
one undifferentiated dim mass. It still sorts last.

`highlightColor` and `visitedLinkColor` are deliberately left unclaimed, for
the overflow badge and any future selection affordance.

## Tool classes

`tool` was one glyph. `tool_name` is captured on `PreToolUse` — it is the only
non-universal field the probe ever saw populated — so the class is free.

| Class | Tools | Glyph |
|---|---|---|
| command | `Bash` | ▶ |
| edit | `Edit`, `Write`, `NotebookEdit` | ✎ |
| read | `Read`, `Grep`, `Glob` | ⌕ |
| network | `WebFetch`, `WebSearch` | ⇅ |
| agent | `Task` | ⑂ |
| other | anything unrecognised | ⚙ |

All take `linkColor`. `other` is the honest fallback: ⚙ means *a tool is
running* and the popup names it. A new tool in a Claude Code release lands here
rather than being mislabelled.

`agent` is the only visibility the panel has into subagent work — see the open
question about top-level sessions.

## Error kinds

`error` was one glyph. Finding C established that `matcher` never reaches the
payload, so `error_kind` must come from matcher-specific registrations passing
the kind as a literal argument. That registration is required anyway, so the
kinds arrive whether or not they are rendered.

| Kind | Glyph | Meaning |
|---|---|---|
| `rate_limit` | ⏳ | it will recover on its own; wait |
| `overloaded` | ☁ | upstream, will retry |
| `billing_error` | 💳 | it will not recover; act |
| unknown or unregistered | ⛔ | kind not captured |

All keep `negativeTextColor`. The wait-versus-act distinction is the point:
`rate_limit` needs nothing from you, `billing_error` needs you now, and under
the old single ⛔ they were indistinguishable.

Deliberately *not* given `neutralTextColor` despite recovering by itself — that
role belongs to `waiting-permission`, and reusing it would undo the one role per
state rule.

## Intensity ramp

The binary stale flag becomes a continuous ramp.

- Full intensity until the state's transient threshold —
  `TRANSIENT_THINKING_SECS` (300) or `TRANSIENT_TOOL_SECS` (1800).
- Then a linear fade to a floor as elapsed approaches `IDLE_EVICT_SECS` (900).
- Floor is 0.4, not 0, so a stale session stays readable.
- Attention states — `error`, `waiting-permission`, `waiting-elicitation` — do
  not ramp. Something waiting on you does not become less true with time.

The evaluator emits `intensity` as a float. It is a derived value, so it is
computed there and nowhere else, per the existing invariant that no derived
value is computed in QML.

## Ordinals, for several sessions in one project

The existing Labels decision adds a discriminator to the popup only when two
live sessions collide. The panel row needs the same, because two glyphs for one
project are otherwise indistinguishable.

- An ordinal appears **only when a project has more than one live session**. One
  session per project, the common case, stays clean.
- Rendered as a trailing superscript: ¹ ² ³ … ⁹, then ⁺ beyond nine.
- Same theme role as the state, so it does not introduce a channel of its own.
- **Sticky.** An ordinal is claimed when a session is first seen and released at
  `SessionEnd`. A new session takes the lowest free ordinal. Ordinals therefore
  do not renumber when a sibling exits — a glyph you have learnt to recognise
  keeps its number for as long as it lives.
- Ordinal order is by claim, which for simultaneous starts is by start instant,
  matching the popup's ordering.

Sticky is chosen over rank-among-live deliberately. Recomputed ranks are denser
but renumber under you, which is precisely the failure the panel exists to
avoid.

## Project identity

A hue derived from the session `cwd`, drawn as a thin rule beneath the glyph.
Never on the glyph itself, so state colour and project colour never compete for
one channel.

**This is the one exception to the no-hex-literals invariant**, and it is scoped:
the derived project hue may be a computed colour, it applies only to the project
rule, and it never encodes state. Everything else stays a theme role.

The derivation is the one already shipped in
`identicon/claude-state-identicon.py` — md5 of the absolute path, digest byte 15
for the hue. Sharing it means a Konsole tab and a panel glyph agree on a
project's colour without either knowing about the other. Factoring the two to a
single implementation is Phase 1 work; the rule is that they must not drift.

## What the evaluator must emit

Additions to the per-session object. All derived, all computed once:

| Field | Type | Notes |
|---|---|---|
| `tool_class` | string or null | one of the six classes; null unless state is `tool` |
| `error_kind` | string or null | null unless state is `error`; null too when unregistered |
| `intensity` | float | 0.4 to 1.0; always 1.0 for attention states |
| `ordinal` | int or null | null unless the project has more than one live session |
| `project_hue` | int | 0 to 359 |
| `glyph` | string | resolved, including subtype |
| `role` | string | Kirigami role name, not a colour value |

Renderers select on `glyph` and `role`. They resolve `role` to a colour through
the theme and do nothing else. `doctor` prints all seven fields, so the panel
and the CLI still cannot disagree.

## Rendering notes

Glyph advance widths differ. The row must reserve a fixed slot per session and
centre within it, rather than laying glyphs out in a text flow, or the row will
jitter as states change.

**A colour-emoji glyph paints its own colour and overrides the theme role**,
breaking the one role per state rule for that state alone. The suspects are
⛔ ❗ ❓ ⏳ 💳 ☁ — and note that ⛔ ❗ ❓ are inherited from the spec §5 table, so
this is a pre-existing problem rather than one the vocabulary introduced. If ⛔
renders as colour emoji, `error` is the state that loses its role, which is the
worst one to lose.

This is **unverified**. Deciding it needs the Unicode `Emoji_Presentation`
property, which the standard library does not expose and which could not be
fetched from here, and in any case the outcome depends on the user's font
configuration rather than on Unicode alone. Item 15 settles it by rendering. If
a glyph does come out in colour, the fix is a text-presentation substitute, not
a variation selector — `U+FE0F` forces emoji, and the opposite request
`U+FE0E` is widely ignored.

## Collapse order

This is more than the panel probably needs. When it comes to pruning, in
increasing order of what is lost:

1. **Tool classes** → back to a single ⚙. The popup already names the tool, and
   the distinction matters least when you are not looking at that session.
2. **Intensity ramp** → back to a binary stale flag, if the fade reads as noise
   rather than as age.
3. **Project rule** → drop, if the ordinal alone is enough to tell sessions
   apart and the extra rule crowds the row.
4. **Error kinds** → back to a single ⛔. Cheapest to keep, since the data
   arrives regardless, and the wait-versus-act distinction is the most
   actionable thing here.
5. **One role per state** → keep. It costs nothing and it is the only change
   that makes colour carry information rather than repeat it.

Ordinals are not on the list. Two indistinguishable glyphs for one project is
the bug this whole section exists to fix.

## Open questions

Added to `findings.md` as items 14 and 15.

- Are subagent sessions ever tracked as sessions in their own right, or do hooks
  only fire for top-level ones? The panel assumes the latter, which makes *top
  level* automatic rather than something to detect, and makes the `agent` tool
  class the only subagent visibility. Unverified.
- Do ⛔ ❗ ❓ ⏳ 💳 ☁ render monochrome under the user's fonts, or as colour emoji
  that override the theme role? Affects three glyphs inherited from the spec,
  not only the new ones.
