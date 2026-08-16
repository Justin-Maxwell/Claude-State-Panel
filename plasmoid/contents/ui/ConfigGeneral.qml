/*
 * General settings page.
 * SPDX-License-Identifier: AGPL-3.0-or-later
 */

import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kcmutils as KCM
import org.kde.kirigami as Kirigami

KCM.SimpleKCM {
    property alias cfg_command: commandField.text
    property alias cfg_pollInterval: pollField.value
    property alias cfg_slotCount: slotField.value

    Kirigami.FormLayout {

        QQC2.TextField {
            id: commandField
            Kirigami.FormData.label: "Command:"
            Layout.fillWidth: true
            placeholderText: "$HOME/.local/bin/claude-state-panel"
        }
        QQC2.Label {
            text: "Leave blank to use ~/.local/bin/claude-state-panel.\n"
                  + "Set an absolute path to run it from a repo checkout."
            font: Kirigami.Theme.smallFont
            opacity: 0.7
        }

        Item { Kirigami.FormData.isSection: true }

        QQC2.SpinBox {
            id: pollField
            Kirigami.FormData.label: "Poll every:"
            from: 1000
            to: 120000
            stepSize: 1000
            textFromValue: function (value) { return (value / 1000) + " s" }
            valueFromText: function (text) { return parseInt(text) * 1000 }
        }
        QQC2.Label {
            text: "Each poll runs `claude agents --json`, so this is a real\n"
                  + "cost rather than a free timer."
            font: Kirigami.Theme.smallFont
            opacity: 0.7
        }

        Item { Kirigami.FormData.isSection: true }

        QQC2.SpinBox {
            id: slotField
            Kirigami.FormData.label: "Sessions shown:"
            from: 1
            to: 12
        }
        QQC2.Label {
            text: "Sessions beyond this collapse into one overflow badge,\n"
                  + "which carries the most urgent hidden session's glyph."
            font: Kirigami.Theme.smallFont
            opacity: 0.7
        }
    }
}
