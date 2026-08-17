plasmoid_id := "nz.jaymax.claudestatepanel"
identicon := "identicon/claude-state-identicon.py"

# List available recipes
default:
    @just --list

# Run the headless test suite. Requires no Plasma shell and no live session.
test:
    python3 -m unittest discover -s tests -v

# Run the suite under three timezones. Raw epochs must be identical across all
# three; only localised strings may differ.
test-tz:
    TZ=Pacific/Auckland python3 -m unittest discover -s tests
    TZ=UTC python3 -m unittest discover -s tests
    TZ=America/New_York python3 -m unittest discover -s tests

# Human-readable diagnostic render of current state (Phase 1 onward)
doctor:
    bin/claude-state-panel doctor

# Raw evaluator output as JSON (Phase 1 onward)
eval:
    bin/claude-state-panel eval

# Symlink the CLI into ~/.local/bin, which is where the plasmoid looks by
# default. Points at the checkout, so edits take effect without reinstalling
# and there is still exactly one copy of the evaluator on the machine.
install-cli:
    mkdir -p ~/.local/bin
    ln -sfn {{justfile_directory()}}/bin/claude-state-panel ~/.local/bin/claude-state-panel
    ~/.local/bin/claude-state-panel doctor

# Remove the symlink
uninstall-cli:
    rm -f ~/.local/bin/claude-state-panel

# --- Konsole project identicons -------------------------------------------
# Manual for now: nothing is wired to a hook. See docs/konsole-identicons.md.

# Derived names and a terminal preview for the current project
identicon-show:
    {{identicon}} show

# Install the current project's identicon into the user icon theme
identicon-install:
    {{identicon}} install

# Report which session D-Bus methods this Konsole build actually exposes
identicon-probe:
    {{identicon}} probe

# Probe, then exercise both the badge and profile routes on this tab
identicon-demo:
    {{identicon}} demo

# Remove the current project's identicon and generated profile
identicon-uninstall:
    {{identicon}} uninstall

# Environment report for the identicon tool
identicon-doctor:
    {{identicon}} doctor

# Print the identicon as it appears on a return of control
identicon-emit:
    {{identicon}} emit

# Print the hook registration to paste into ~/.claude/settings.json
identicon-hooks:
    {{identicon}} hooks

# Install the plasmoid
install-plasmoid:
    kpackagetool6 --type Plasma/Applet --install plasmoid/

# Upgrade an already-installed plasmoid in place
upgrade-plasmoid:
    kpackagetool6 --type Plasma/Applet --upgrade plasmoid/

# Remove the plasmoid
uninstall-plasmoid:
    kpackagetool6 --type Plasma/Applet --remove {{plasmoid_id}}

# Run the widget standalone, without touching the running panel
preview:
    plasmoidviewer -a plasmoid/

# Restart the shell. Development only — never part of an install.
reload-plasmashell:
    systemctl --user restart plasma-plasmashell.service

# Build a distributable package
package:
    cd plasmoid && zip -r ../{{plasmoid_id}}.plasmoid . -x '*.git*'
