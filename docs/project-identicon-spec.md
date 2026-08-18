# Project identicon specification

A deterministic visual identity for a software project, derived from the project
itself and from nothing else. Any tool implementing this specification produces
the same identicon for the same project as any other, without coordination,
configuration, or a shared registry.

The valuable half of this document is **the key** — deciding what identifies a
project. The other half, how a key becomes a pattern, should come from an
established identicon implementation rather than from here; the derivation
below records what the tool does today and is not a standard worth conforming
to.

## Why it exists

Several tools in and around this repository need to answer *which project is
this*, in different media:

| Consumer | Medium | Uses |
|---|---|---|
| Return-of-control hook | terminal, ANSI | grid and colour |
| Konsole tab | icon theme PNG, profile | grid and colour |
| Konsole session badge | terminal overlay | label and colour |
| Panel glyph row | Qt Quick | colour only |

They must agree. A tab, a panel glyph and a terminal banner disagreeing about a
project's colour would be worse than none of them having one.

## Scope

**In:** how to derive a key, and how a key reaches each medium. **Out:** where
any tool chooses to display the result, and what it does with the rest of its
interface.

## The key

Everything derives from one string. Getting the key right matters more than
anything else here, because two tools that disagree about the key agree about
nothing else.

### Resolution order

Resolve most specific first, and stop at the first that yields a value:

| # | Source | Key | Portable |
|---|---|---|---|
| 1 | `explicit` | supplied by the caller | — |
| 2 | `override` | first non-blank, non-`#` line of `.repository-identicon` at the repository top level, whitespace-stripped | yes, if committed |
| 3 | `remote` | the normalised git remote, below | **yes** |
| 4 | `toplevel` | the repository top level, as an absolute path | no |
| 5 | `path` | the directory itself, as an absolute path | no |

Sources 3 and 2 are the only ones that survive being cloned elsewhere. An
implementation SHOULD report which source it used, because a project silently
falling back to a path key will change identity when checked out on another
machine, and that is worth seeing before it happens rather than after.

The override file was formerly `.claude-state-identicon`, named for one
consumer of a specification that has several and none of which is Claude. An
implementation SHOULD still honour that name where the current one is absent,
and MUST prefer the current one where both exist: the file is committed into
other people's repositories, and dropping it silently changes the identity it
was written to pin — the one outcome an override exists to prevent.

The git remote is `origin` where one exists, otherwise the first remote listed.

**Why not the path.** A path is not stable across machines, containers, cloud
sessions, or worktrees. That last one is decisive rather than theoretical: a git
worktree keeps the same `origin` but has its own top level, and Claude Code's
desktop app gives every parallel session its own worktree. A path key would
therefore give each parallel session in one project a different identity —
precisely inverting what an identicon is for.

A session started in a subdirectory has the same failure and the same fix, since
`rev-parse --show-toplevel` reports the repository root from anywhere inside it.

### Remote normalisation

Every spelling of one repository MUST collapse to one key. Given a remote URL:

1. Trim whitespace; strip a trailing `/`.
2. Reject if empty, if it begins with `/`, or if the scheme is `file`. A
   local-path remote is no more portable than the working directory and earns no
   special treatment.
3. If the URL contains `://`, take the authority as everything up to the next
   `/`, and the path as the remainder. Otherwise, if it contains `:`, treat it
   as scp-like: authority before the first `:`, path after. Otherwise reject.
4. In the authority, discard everything up to and including the last `@`, then
   discard any `:port`. What remains is the host.
5. Strip `/` from both ends of the path, then strip a trailing `.git`,
   case-insensitively.
6. Reject if either the host or the path is now empty.
7. The key is the host and the path segments, joined by `/`, **lowercased**.

Lowercasing is deliberate: forges treat owner and repository names
case-insensitively, so `Owner/Repo` and `owner/repo` are one project.

The host is retained, so `github.com/a/b` and `gitlab.com/a/b` stay distinct.

All of these MUST yield `github.com/owner/repo`:

```
https://github.com/Owner/Repo.git      git@github.com:Owner/Repo.git
https://github.com/Owner/Repo          git@github.com:Owner/Repo
https://github.com/owner/repo/         ssh://git@github.com/Owner/Repo.git
https://token@github.com/Owner/Repo.git    ssh://git@github.com:2222/Owner/Repo.git
https://user:pass@github.com/Owner/Repo.git    git://github.com/Owner/Repo.git
```

## The pattern

GitHub-style: a 5×5 grid, mirrored, so every identicon is vertically symmetric
and reads as a deliberate mark rather than as noise.

Let `h` be the **MD5 digest of the key encoded as UTF-8, as lowercase hex**,
thirty-two characters.

```
grid[row][col] = false for all row, col in 0..4

for index in 0..14:
    painted = hexval(h[index]) mod 2 == 0
    col, row = index div 5, index mod 5
    grid[row][2 - col] = painted
    grid[row][2 + col] = painted
```

The first fifteen hex **characters** are consumed, one per cell, drawn down the
middle column first and then mirrored outwards: characters 0-4 fill column 2,
5-9 fill columns 1 and 3, 10-14 fill columns 0 and 4. Even is foreground.

Note this indexes hex characters, not digest bytes, and works centre-out rather
than left-to-right. Both details are inherited rather than chosen — see
**Where these constants come from** below.

MD5 is used because this is an identity function, not a security one. It must
be fast, stable, and available everywhere.

## The colour

```
hue        = hexval(h[-7:]) / 0xfffffff      the last seven hex characters
saturation = 0.7
lightness  = 0.5
```

The hue is drawn from the same digest as the grid, so colour and pattern cannot
drift apart. Saturation and lightness are fixed rather than derived.

Convert HSL to RGB by the standard formula. Quantise each component as:

```
component_255 = floor(component * 255 + 0.5)
```

**Round half up, not half to even.** Stated explicitly because Python's `round`
is half to even while most languages' native rounding is half up; following the
reference language's default would have made this specification quietly
unportable.

### Where these constants come from

Every number above — the centre-out hex-character walk, the seven-character hue
draw, `0.7` and `0.5` — is taken from **`stewartlord/identicon.js`**, vendored at
`identicon/reference/vendor/identicon.js` and pinned by `identicon/vectors.json`.
None of them is ours.

That is deliberate, and it is the reason to state it here rather than to justify
each value on its merits. The PNGs are produced through that library, so any
constant we picked independently would be a second opinion that the rendered
image would immediately contradict. Deferring to the library removes the
decision entirely: there is one source, and conformance is testable rather than
arguable. An earlier draft of this document specified `saturation = 0.55` and a
byte-indexed left-to-right grid; both were plausible, neither matched what
shipped, and the committed identicon disagreed with its own specification until
this was reconciled.

The corollary is that these values are not defended, only recorded. If the
vendored library is ever replaced, they change with it, and this section is
where to look.

Note that fixed-lightness HSL clusters perceptually: the hue draw is uniform, but
equal hue steps are not equally visible, so the green band reads as one colour
across roughly 50 degrees. A perceptually uniform space would fix it, and this
is a known cost of taking the colour from the reference rather than choosing it.

## Derived names

From `sha256(key)` as lowercase hex, take:

| Name | Definition | Purpose |
|---|---|---|
| short id | first **12** characters | icon file names, uniqueness |
| discriminator | first **6** characters | distinguishing two projects that share a basename |

The project name is the last `/`-separated segment of the key, or the key itself
if it contains no `/`.

An icon theme name is `<tool-prefix>-<short id>`. The prefix belongs to the
implementing tool; this repository uses `claude-state-identicon-`. The
specification fixes the short id, not the prefix, so two tools installing icons
into the same theme do not collide.

**Badge label**, for media that can only show one or two characters: split the
project name on `-`, `_`, `.` and space. If two or more parts result, take the
first character of each of the first two. Otherwise take the first two
characters of the name. Upper-case the result.

## Renderings

### Raster

A square canvas of side `size`:

```
cell = max(1, floor(size / 5.5 + 0.5))
if cell * 5 > size: cell = max(1, floor(size / 5))
margin = floor((size - cell * 5) / 2)
```

Cells are generous relative to the canvas so that a 16-pixel icon still reads as
a pattern. Filled cells take the colour; everything else is transparent by
default.

### Terminal

**Send the real image where the terminal can take one.** Text blocks are an
approximation of a 5×5 grid; an inline image is the grid. An implementation
SHOULD prefer, in order:

1. **iTerm2 inline image protocol**, `OSC 1337`. The raster PNG, base64, in
   `ESC ] 1337 ; File = <args> : <base64> BEL`. Arguments SHOULD include
   `inline=1`, `size=<byte count>` and `preserveAspectRatio=1`. **No argument
   may contain a colon**, since the colon terminates the argument list and
   begins the payload.
2. **kitty graphics protocol**, `APC _G`. `a=T,f=100`, base64 payload chunked at
   4096 characters, every chunk but the last carrying `m=1`.
3. **Text blocks**, below.

Konsole implements the iTerm2 protocol: `Vt102Emulation::osc_put` matches the
literal `1337;File=` and then waits for the `:` terminator, so arguments between
the two are accepted and ignored. It also handles kitty APC graphics and sixel.
Because Konsole ignores the protocol's own width and height arguments, the PNG's
own pixel size decides how large the identicon lands; 40 pixels is about two
text rows.

Protocol selection SHOULD be by environment — `KITTY_WINDOW_ID` or a `TERM`
containing `kitty`; `KONSOLE_VERSION` or `KONSOLE_DBUS_SESSION`; a known
`TERM_PROGRAM`. It MUST NOT be by querying the terminal and waiting for a reply:
this runs in a hook, and a reply that never comes hangs the turn.

**Nothing but the identicon is printed.** No project name, no key, no label. The
mark is the message.

### Text blocks, the fallback

Two grid rows per text row, drawn with `U+2580 UPPER HALF BLOCK`: foreground is
the identicon colour where the upper grid row is filled, background where the
lower one is. The fifth grid row pairs with a blank row. This gives **five
characters wide by three tall**, which comes out roughly square given typical
cell aspect. All 25 cells are represented; only the resolution is lost.

Colour depth SHOULD be chosen as: `NO_COLOR` set in the environment means no
colour at all, per no-color.org, and also suppresses inline images; `COLORTERM`
of `truecolor` or `24bit` means 24-bit; otherwise the xterm 256-colour cube,
`16 + 36r + 6g + b` with each component quantised as `floor(c * 5 / 255 + 0.5)`.

Without colour, the grid MUST still be legible, since colour is never allowed to
be the only channel: use `█` for both rows filled, `▀` for the upper only, `▄`
for the lower only, and a space for neither.
