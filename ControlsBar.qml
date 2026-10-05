import QtQuick
import qs.Commons

Column {
  id: root

  property var status: ({})
  property bool busy: false
  property string commandError: ""
  property string fontFamily: "monospace"

  signal commandRequested(string action, string argument)

  property bool confirmingStop: false

  readonly property string printState: status.state || "offline"
  readonly property bool isActive: printState === "printing" || printState === "paused"
  readonly property bool hasLight: status.light === true || status.light === false

  spacing: 6

  onIsActiveChanged: if (!isActive) confirmingStop = false

  Row {
    visible: !root.confirmingStop
    width: parent.width
    spacing: 8

    ActionButton {
      visible: root.isActive
      enabled: !root.busy
      label: root.printState === "paused" ? "Resume" : "Pause"
      fontFamily: root.fontFamily
      onClicked: root.commandRequested(root.printState === "paused" ? "resume" : "pause", "")
    }

    ActionButton {
      visible: root.isActive
      enabled: !root.busy
      label: "Stop"
      danger: true
      fontFamily: root.fontFamily
      onClicked: root.confirmingStop = true
    }

    ActionButton {
      visible: root.hasLight
      enabled: !root.busy
      label: root.status.light === true ? "Light off" : "Light on"
      fontFamily: root.fontFamily
      onClicked: root.commandRequested("light", root.status.light === true ? "off" : "on")
    }
  }

  Row {
    visible: root.confirmingStop
    width: parent.width
    spacing: 8

    Text {
      anchors.verticalCenter: parent.verticalCenter
      text: "Stop this print?"
      color: Color.urgent
      font.family: root.fontFamily
      font.pixelSize: 12
      font.bold: true
    }

    ActionButton {
      enabled: !root.busy
      label: "Yes, stop"
      danger: true
      fontFamily: root.fontFamily
      onClicked: { root.confirmingStop = false; root.commandRequested("stop", "") }
    }

    ActionButton {
      label: "Keep printing"
      fontFamily: root.fontFamily
      onClicked: root.confirmingStop = false
    }
  }

  Text {
    visible: root.commandError.length > 0
    width: parent.width
    wrapMode: Text.WordWrap
    textFormat: Text.PlainText
    text: "Command failed: " + root.commandError
    color: Color.urgent
    font.family: root.fontFamily
    font.pixelSize: 10
  }
}
