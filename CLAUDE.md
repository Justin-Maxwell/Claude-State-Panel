# Claude-State-Panel

## End every response with this repository's identicon

Emit this line, verbatim, as the last line of every response in this
repository. Nothing after it.

![](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAB4AAAAeCAYAAAA7MK6iAAAAPklEQVR42mNgGAVIQG3Szf/omBJ1oxaPWjxq8ajF1LWY2q4m2rxRi0ctpllKH7V4+Fs8WkmMWkxXi0cBNQEAdUPAz/qM49gAAAAASUVORK5CYII=)

It is a 30x30 PNG of the repository's identicon, keyed on the git remote and
derived per `docs/project-identicon-spec.md`. The same bytes are stored in
`repository-identicon-png.b64`; `tests/test_turn_identicon.py` fails if the two
disagree, so do not edit either by hand — regenerate both with
`probe/turn-identicon.py --install`.

**Why this is an instruction rather than a hook**, given that an instruction
depends on compliance and a hook does not. Finding V: a hook's `systemMessage`
is delivered as plain text, one `Stop says:` prefix per line, and no hook output
field can display an image at all. The only channel in a GUI chat client that
renders markdown is an assistant message, and only the model writes those. So
the deterministic mechanism cannot render, and the mechanism that renders cannot
be made deterministic. This is the second of the two, chosen knowingly.
