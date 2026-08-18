# Claude-State-Panel

## Sign every response with this repository's identicon

Emit this line, verbatim, as the last line of every response in this
repository. Nothing after it.

**Also emit it immediately before asking anything** — as the last line of the
text preceding a question, including before a tool call that puts a question to
the user. A turn that ends in a question may never reach a turn-end at all, so
it is both the turn most likely to lose the mark and the one where the reader
most needs it: they are being asked to stop and decide, and which project is
asking is part of the question.

![](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABYAAAAWCAYAAADEtGw7AAAAMklEQVR42mNgoCdQm3TzPzImVX7U4FGDB8Jgsl1ASP+owVSLrFGDqZ+uR8sKqqV7igAAJiPDEHA0udMAAAAASUVORK5CYII=)

It is a 22x22 PNG of the repository's identicon — a 5x5 grid of 4-pixel cells
inside a 1-pixel border — keyed on the git remote and derived per
`docs/project-identicon-spec.md`.

`.identicon/` holds the same mark in every form a consumer might want, each
usable with no parsing at all:

| file | for |
|---|---|
| `.identicon/repository-identicon.png` | a README, or anywhere that refuses SVG |
| `.identicon/repository-identicon.svg` | a README on a forge that renders it; anything scalable |
| `.identicon/repository-identicon.colour` | `#rrggbb`, for a prompt, a badge, or a theme |

Each name repeats the directory on purpose, so a file still says what it is once
it has been copied somewhere else. The literal above is base64 of the PNG — the
one form no file can provide, since a `data:` URI carries its bytes rather than
referencing a path.

`tests/test_turn_identicon.py` fails if any of them disagree with each other or
with a fresh derivation, so do not edit any by hand — regenerate the set with
`/repo-identicon`.

That skill is also how you give **another** repository an identicon. It carries
its own copy of the derivation and needs nothing from this checkout; the
conformance apparatus — the vendored identicon.js and its pinned vectors —
stays here, and the test suite holds the two implementations to each other.

**Why this is an instruction rather than a hook**, given that an instruction
depends on compliance and a hook does not. Finding V: a hook's `systemMessage`
is delivered as plain text, one `Stop says:` prefix per line, and no hook output
field can display an image at all. The only channel in a GUI chat client that
renders markdown is an assistant message, and only the model writes those. So
the deterministic mechanism cannot render, and the mechanism that renders cannot
be made deterministic. This is the second of the two, chosen knowingly.
