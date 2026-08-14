plasmoid_id := "nz.jaymax.claudestatepanel"

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
