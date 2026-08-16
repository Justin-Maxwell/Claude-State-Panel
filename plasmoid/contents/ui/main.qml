/*
 * Claude State Panel -- the plasmoid.
 *
 * Renderer only. Every decision about what a session's state is, which sessions
 * get a slot, what order they sit in, which glyph and which colour they carry,
 * and what the overflow badge shows, is made by the evaluator and arrives here
 * as JSON. Nothing in this file recomputes any of it -- that is what stops the
 * panel and `claude-state-panel doctor` from ever disagreeing.
 *
 * If you find yourself wanting to add a condition here that decides something
 * about a session, it belongs in evaluator/claude-state-eval.py instead.
 *
 * Open question 5 was "the correct Plasma 6 QML import and API for the
 * executable data engine". Answered by observation rather than documentation:
 * org.kde.plasma.plasma5support, DataSource with engine "executable", drive it
 * with connectSource() and hang up in onNewData. Two widgets already installed
 * on this machine use exactly this and work.
 *
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */

import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.components as PlasmaComponents
import org.kde.plasma.extras as PlasmaExtras
import org.kde.plasma.plasma5support as P5Support
import org.kde.kirigami as Kirigami

PlasmoidItem {
    id: root

    // ---- configuration ----
    // The command is resolved here rather than defaulted in main.xml so that
    // KConfig never sees a "$HOME" it might try to interpret. The executable
    // engine runs through a shell, so the shell expands it.
    readonly property string command: Plasmoid.configuration.command !== ""
        ? Plasmoid.configuration.command
        : "\"$HOME/.local/bin/claude-state-panel\""
    readonly property int pollMs: Plasmoid.configuration.pollInterval
    readonly property int slotCount: Plasmoid.configuration.slotCount

    // "state": the dot is the state, one thing to read.
    // "project": the dot is the project, state becomes a ring around it.
    readonly property bool fillIsProject: Plasmoid.configuration.dotFill === "project"

    // ---- state, straight from the evaluator ----
    property var model: null
    property string errorMsg: ""
    property bool everLoaded: false

    readonly property var sessions: model ? model.sessions : []
    readonly property var overflow: model ? model.overflow : null
    readonly property int attentionCount: model ? model.attention_count : 0
    readonly property int sessionCount: model ? model.session_count : 0

    Plasmoid.icon: "utilities-terminal"
    Plasmoid.status: attentionCount > 0
        ? PlasmaCore.Types.ActiveStatus
        : PlasmaCore.Types.PassiveStatus

    toolTipMainText: "Claude State"
    toolTipSubText: {
        if (errorMsg !== "") return errorMsg
        if (!everLoaded) return "Reading…"
        if (sessionCount === 0) return "No Claude Code sessions"
        var line = sessionCount + (sessionCount === 1 ? " session" : " sessions")
        return attentionCount > 0
            ? line + ", " + attentionCount + " waiting on you"
            : line + ", none waiting on you"
    }

    /*
     * Colour names, not hex, come out of the evaluator. Mapping them onto the
     * live Kirigami theme here is what makes the widget follow the user's
     * colour scheme instead of overriding it.
     */
    /*
     * The palette. Literal colours rather than Kirigami theme roles, which is a
     * deliberate departure from the usual advice and worth justifying.
     *
     * Kirigami offers positive/neutral/negative/highlight, which is three
     * usable semantic colours plus the user's accent. This widget needs four
     * that stay distinguishable from each other at a glance, and the accent is
     * whatever the user picked -- if theirs is orange, an accent-blue "idle"
     * would collide with "needs a decision". State legibility is the entire
     * product here, so it wins over scheme-matching.
     *
     * Chosen to hold up against both light and dark panel backgrounds.
     */
    readonly property var palette: ({
        "none":      "#2e7d32",  // dark green  -- working, nothing required
        "available": "#2196f3",  // blue        -- idle, your turn
        "attention": "#ffc107",  // amber       -- blocked, needs an answer
        "urgent":    "#ff6d00",  // orange      -- blocked, needs a decision
        "neutral":   "#9e9e9e"   // grey        -- unclassified
    })

    function colourFor(name) {
        // A role this file has never heard of falls back to grey rather than
        // rendering nothing. A test asserts every role the evaluator emits has
        // an entry above, so this path means the evaluator gained a role and
        // the palette was not updated.
        return palette[name] !== undefined ? palette[name] : palette["neutral"]
    }

    // ---- polling ----
    P5Support.DataSource {
        id: exec
        engine: "executable"
        connectedSources: []

        onNewData: (sourceName, data) => {
            // Hang up immediately: the source is one-shot, and leaving it
            // connected re-runs the command on every internal tick.
            disconnectSource(sourceName)

            if (data["exit code"] !== 0 && data["stdout"] === "") {
                root.errorMsg = "cannot run " + root.command
                return
            }
            try {
                var parsed = JSON.parse(data["stdout"])
                root.model = parsed
                root.everLoaded = true
                // A warning with no sessions means we could not look. A warning
                // with sessions means one session was odd -- keep displaying.
                root.errorMsg = (parsed.warnings && parsed.warnings.length > 0
                                 && parsed.sessions.length === 0)
                    ? parsed.warnings[0] : ""
            } catch (e) {
                root.errorMsg = "unreadable output from " + root.command
            }
        }
    }

    function poll() {
        exec.connectSource(root.command + " eval --slots " + root.slotCount)
    }

    Timer {
        interval: root.pollMs
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: root.poll()
    }

    // Repoll the moment the popup opens, so opening it never shows a stale
    // frame while waiting for the next tick.
    onExpandedChanged: if (expanded) poll()

    /*
     * Clipboard. QtQuick exposes no clipboard API, and the standard workaround
     * is an off-screen TextEdit: setting text, selecting it and calling copy()
     * puts it on the clipboard. Kept in one place so the popup can just call
     * copyToClipboard().
     */
    TextEdit {
        id: clipboardProxy
        visible: false
    }
    function copyToClipboard(text) {
        clipboardProxy.text = text
        clipboardProxy.selectAll()
        clipboardProxy.copy()
        clipboardProxy.text = ""
    }

    // ---- compact: one glyph per session, plus the overflow badge ----
    compactRepresentation: MouseArea {
        id: compact

        readonly property bool vertical: Plasmoid.formFactor === PlasmaCore.Types.Vertical

        /*
         * Dots are drawn, not typed. The first version used the text glyphs
         * "●" and "○", which cannot be sized honestly -- a bullet occupies
         * roughly a third of its font's em box, so asking for a given diameter
         * means guessing a font size and hoping. Drawing a circle makes the
         * diameter mean the diameter.
         *
         * Size follows the panel's own thickness rather than a fixed number, so
         * the widget suits a slim panel and a fat one without configuration.
         * The cross axis is the free one -- the panel sets it -- so reading it
         * here creates no binding loop, provided the cross axis's preferred
         * size below is NOT derived from content. It is not.
         */
        readonly property int thickness: vertical ? width : height
        readonly property int dotSize: Math.max(Kirigami.Units.iconSizes.small,
                                                Math.round(thickness * 0.62))

        /*
         * Docking in a panel, horizontal or vertical.
         *
         * A panel fixes the applet's *cross* axis -- that is the panel's own
         * thickness, and the applet does not get a say -- and asks the applet
         * how much it wants along the *main* axis. So the main axis is pinned
         * with minimum == maximum == the content size, and the cross axis is
         * left free between a small floor and infinity.
         *
         * Getting this wrong does not produce an error. It produces an applet
         * that collapses to zero along one axis, which looks exactly like a
         * widget that refused to be added to the panel at all. The first
         * version of this file set only minimums, and zero on the cross axis.
         */
        readonly property int contentWidth: glyphRow.implicitWidth
                                            + Kirigami.Units.smallSpacing * 2
        readonly property int contentHeight: glyphRow.implicitHeight
                                             + Kirigami.Units.smallSpacing * 2
        readonly property int floorSize: Kirigami.Units.iconSizes.small

        Layout.minimumWidth: vertical ? floorSize : contentWidth
        Layout.maximumWidth: vertical ? Number.POSITIVE_INFINITY : contentWidth
        // Preferred size on the CROSS axis must be a constant, never content:
        // dotSize is derived from the cross axis, so feeding content back into
        // it would close a binding loop.
        Layout.preferredWidth: vertical ? floorSize : contentWidth

        Layout.minimumHeight: vertical ? contentHeight : floorSize
        Layout.maximumHeight: vertical ? contentHeight : Number.POSITIVE_INFINITY
        Layout.preferredHeight: vertical ? contentHeight : floorSize

        acceptedButtons: Qt.LeftButton
        onClicked: root.expanded = !root.expanded

        GridLayout {
            id: glyphRow
            anchors.centerIn: parent
            flow: compact.vertical ? GridLayout.TopToBottom : GridLayout.LeftToRight
            // Gaps scale with the dots, so the strip keeps its rhythm on a slim
            // panel and a fat one alike.
            columnSpacing: Math.max(2, Math.round(compact.dotSize * 0.3))
            rowSpacing: columnSpacing

            Repeater {
                model: root.sessions
                delegate: Rectangle {
                    required property var modelData
                    Layout.preferredWidth: compact.dotSize
                    Layout.preferredHeight: compact.dotSize
                    radius: width / 2
                    antialiasing: true

                    // In project mode the fill identifies *which* session and
                    // the ring says what it wants; the ring is drawn thick so
                    // that "wants something" still wins the glance, since that
                    // is the question the widget exists to answer.
                    color: root.fillIsProject ? modelData.project_colour
                                              : root.colourFor(modelData.colour)
                    border.width: root.fillIsProject
                        ? Math.max(2, Math.round(compact.dotSize * 0.18)) : 0
                    border.color: root.colourFor(modelData.colour)
                }
            }

            // The badge borrows the highest-priority hidden session's colour --
            // decided by the evaluator, not here -- so a hidden session needing
            // attention still reads as needing it. The count sits inside the
            // dot rather than beside it, so the strip stays one shape wide;
            // that matters most in a vertical panel, where anything wider than
            // a dot has nowhere to go.
            Rectangle {
                visible: root.overflow && root.overflow.count > 0
                Layout.preferredWidth: compact.dotSize
                Layout.preferredHeight: compact.dotSize
                radius: width / 2
                antialiasing: true
                color: root.overflow ? root.colourFor(root.overflow.colour)
                                     : root.palette["neutral"]

                PlasmaComponents.Label {
                    anchors.centerIn: parent
                    text: root.overflow ? root.overflow.count : ""
                    color: "white"
                    font.pixelSize: Math.round(compact.dotSize * 0.62)
                    font.bold: true
                }
            }

            // Something to click when there is nothing to show, otherwise the
            // widget becomes a zero-width strip that cannot be opened.
            Rectangle {
                visible: root.sessions.length === 0
                         && (!root.overflow || root.overflow.count === 0)
                Layout.preferredWidth: compact.dotSize
                Layout.preferredHeight: compact.dotSize
                radius: width / 2
                antialiasing: true
                color: "transparent"
                border.width: Math.max(1, Math.round(compact.dotSize * 0.09))
                border.color: root.errorMsg !== ""
                    ? Kirigami.Theme.negativeTextColor
                    : root.palette["neutral"]
            }
        }
    }

    // ---- popup: the same sessions, with enough detail to act on ----
    fullRepresentation: PlasmaExtras.Representation {
        Layout.minimumWidth: Kirigami.Units.gridUnit * 22
        Layout.minimumHeight: Kirigami.Units.gridUnit * 16
        Layout.preferredWidth: Kirigami.Units.gridUnit * 26
        Layout.preferredHeight: Kirigami.Units.gridUnit * 20

        header: PlasmaExtras.PlasmoidHeading {
            RowLayout {
                anchors.fill: parent
                PlasmaExtras.Heading {
                    level: 4
                    text: root.attentionCount > 0
                        ? root.attentionCount + " waiting on you"
                        : (root.sessionCount + (root.sessionCount === 1
                                                ? " session" : " sessions"))
                    color: root.attentionCount > 0
                        ? Kirigami.Theme.neutralTextColor
                        : Kirigami.Theme.textColor
                }
                Item { Layout.fillWidth: true }
                PlasmaComponents.Label {
                    text: root.model ? root.model.generated_at_local : ""
                    opacity: 0.6
                    font: Kirigami.Theme.smallFont
                }
            }
        }

        contentItem: PlasmaComponents.ScrollView {
            ListView {
                id: sessionList
                model: root.model
                    ? root.sessions.concat(root.overflow ? root.overflow.sessions : [])
                    : []
                spacing: Kirigami.Units.smallSpacing
                clip: true

                delegate: PlasmaComponents.ItemDelegate {
                    id: sessionRow
                    required property var modelData
                    width: sessionList.width
                    hoverEnabled: true

                    // Spec: clicking a session copies its cwd. Phase 3 will add
                    // raising the Konsole tab; copying is the useful half that
                    // needs no D-Bus and no window management.
                    onClicked: {
                        root.copyToClipboard(modelData.cwd)
                        copiedFeedback.sessionId = modelData.session_id
                        copiedFeedback.restart()
                    }

                    contentItem: RowLayout {
                        spacing: Kirigami.Units.largeSpacing

                        // Same dot as the panel, so the popup teaches the
                        // colours rather than using a second vocabulary.
                        Rectangle {
                            Layout.preferredWidth: Kirigami.Units.gridUnit
                            Layout.preferredHeight: Kirigami.Units.gridUnit
                            Layout.alignment: Qt.AlignVCenter
                            radius: width / 2
                            antialiasing: true
                            color: root.fillIsProject
                                ? sessionRow.modelData.project_colour
                                : root.colourFor(sessionRow.modelData.colour)
                            border.width: root.fillIsProject ? 3 : 0
                            border.color: root.colourFor(sessionRow.modelData.colour)
                            opacity: sessionRow.modelData.slot === null ? 0.55 : 1.0
                        }

                        /*
                         * The identicon, derived from the project path and so
                         * needing no configuration from anyone.
                         *
                         * Drawn here and deliberately not in the panel: at
                         * panel size a 5x5 grid is mush, whereas the popup has
                         * room for it to be recognisable. Shape is a second,
                         * redundant channel for identity -- useful to anyone
                         * who cannot rely on the colour.
                         */
                        Column {
                            id: identicon
                            readonly property int cell:
                                Math.max(2, Math.round(Kirigami.Units.gridUnit / 5))
                            Layout.alignment: Qt.AlignVCenter
                            Layout.preferredWidth: cell * 5
                            spacing: 0
                            opacity: sessionRow.modelData.slot === null ? 0.55 : 1.0

                            Repeater {
                                model: sessionRow.modelData.identicon
                                delegate: Row {
                                    id: identiconRow
                                    required property string modelData
                                    spacing: 0
                                    Repeater {
                                        model: 5
                                        delegate: Rectangle {
                                            required property int index
                                            width: identicon.cell
                                            height: identicon.cell
                                            // Indexed, not .charAt(): a test
                                            // scans for `modelData.<field>` to
                                            // prove the renderer reads only
                                            // fields the evaluator emits, and a
                                            // method call would read as a field.
                                            color: identiconRow.modelData[index] === "1"
                                                ? sessionRow.modelData.project_colour
                                                : "transparent"
                                        }
                                    }
                                }
                            }
                        }

                        ColumnLayout {
                            spacing: 0
                            Layout.fillWidth: true

                            PlasmaComponents.Label {
                                text: modelData.label
                                font.bold: modelData.attention
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                            PlasmaComponents.Label {
                                text: copiedFeedback.running
                                      && copiedFeedback.sessionId === modelData.session_id
                                    ? "cwd copied"
                                    : modelData.state
                                      + (modelData.slot === null ? "  ·  hidden" : "")
                                opacity: 0.7
                                font: Kirigami.Theme.smallFont
                                elide: Text.ElideRight
                                Layout.fillWidth: true
                            }
                        }

                        PlasmaComponents.Label {
                            text: modelData.age_secs === null
                                ? "" : root.humanAge(modelData.age_secs)
                            opacity: 0.6
                            font: Kirigami.Theme.smallFont
                        }
                    }

                    PlasmaComponents.ToolTip.text: modelData.cwd
                        + "\npid " + modelData.pid + "  ·  click to copy path"
                    PlasmaComponents.ToolTip.visible: hovered
                    PlasmaComponents.ToolTip.delay: Kirigami.Units.toolTipDelay
                }

                PlasmaExtras.PlaceholderMessage {
                    anchors.centerIn: parent
                    width: parent.width - Kirigami.Units.gridUnit * 4
                    visible: sessionList.count === 0
                    iconName: root.errorMsg !== "" ? "dialog-error" : "utilities-terminal"
                    text: root.errorMsg !== "" ? "Cannot read session state"
                                               : "No Claude Code sessions"
                    explanation: root.errorMsg !== "" ? root.errorMsg : ""
                }
            }
        }
    }

    // Transient "copied" acknowledgement. Held here rather than per-delegate so
    // it survives the list re-sorting under a poll.
    Timer {
        id: copiedFeedback
        property string sessionId: ""
        interval: 1500
        onTriggered: sessionId = ""
    }

    function humanAge(seconds) {
        if (seconds === null || seconds === undefined) return ""
        var s = Math.floor(seconds)
        if (s < 60) return s + "s"
        if (s < 3600) return Math.floor(s / 60) + "m"
        var h = Math.floor(s / 3600)
        var m = Math.floor((s % 3600) / 60)
        return h + "h" + (m < 10 ? "0" : "") + m + "m"
    }
}
