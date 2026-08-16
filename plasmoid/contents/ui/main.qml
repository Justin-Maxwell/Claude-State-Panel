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
    function colourFor(name) {
        switch (name) {
        case "attention": return Kirigami.Theme.neutralTextColor
        case "active":    return Kirigami.Theme.positiveTextColor
        case "neutral":   return Kirigami.Theme.disabledTextColor
        // Deliberately the same grey, but reached only by a name this file has
        // never heard of. Kept distinct from "neutral" so the case above is a
        // decision and this one is a fallback -- a test asserts every colour
        // the evaluator emits has its own case, and that only works if the
        // default is not doing double duty.
        default:          return Kirigami.Theme.disabledTextColor
        }
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
        readonly property int glyphSize: Math.round(Kirigami.Units.gridUnit * 0.9)

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
        Layout.preferredWidth: contentWidth

        Layout.minimumHeight: vertical ? contentHeight : floorSize
        Layout.maximumHeight: vertical ? contentHeight : Number.POSITIVE_INFINITY
        Layout.preferredHeight: contentHeight

        acceptedButtons: Qt.LeftButton
        onClicked: root.expanded = !root.expanded

        GridLayout {
            id: glyphRow
            anchors.centerIn: parent
            flow: compact.vertical ? GridLayout.TopToBottom : GridLayout.LeftToRight
            columnSpacing: Kirigami.Units.smallSpacing
            rowSpacing: Kirigami.Units.smallSpacing

            Repeater {
                model: root.sessions
                delegate: PlasmaComponents.Label {
                    required property var modelData
                    text: modelData.glyph
                    color: root.colourFor(modelData.colour)
                    font.pixelSize: compact.glyphSize
                    font.bold: modelData.attention
                }
            }

            // The badge borrows the highest-priority hidden session's glyph and
            // colour -- decided by the evaluator, not here -- so a session
            // needing attention still reads as needing it while hidden.
            PlasmaComponents.Label {
                visible: root.overflow && root.overflow.count > 0
                text: root.overflow ? "+" + root.overflow.count + root.overflow.glyph : ""
                color: root.overflow ? root.colourFor(root.overflow.colour)
                                     : Kirigami.Theme.disabledTextColor
                font.pixelSize: Math.round(compact.glyphSize * 0.8)
                font.bold: root.overflow ? root.overflow.attention : false
            }

            // Something to click when there is nothing to show, otherwise the
            // widget becomes a zero-width strip that cannot be opened.
            PlasmaComponents.Label {
                visible: root.sessions.length === 0
                         && (!root.overflow || root.overflow.count === 0)
                text: root.errorMsg !== "" ? "!" : "·"
                color: root.errorMsg !== "" ? Kirigami.Theme.negativeTextColor
                                            : Kirigami.Theme.disabledTextColor
                font.pixelSize: compact.glyphSize
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

                        PlasmaComponents.Label {
                            text: modelData.glyph
                            color: root.colourFor(modelData.colour)
                            font.pixelSize: Kirigami.Units.gridUnit
                            font.bold: modelData.attention
                            Layout.preferredWidth: Kirigami.Units.gridUnit
                            horizontalAlignment: Text.AlignHCenter
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
