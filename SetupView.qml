import QtQuick
import qs.Commons
import "Format.js" as Format

Column {
  id: root

  property var found: []
  property bool searching: false
  property string fontFamily: "monospace"

  signal searchRequested()
  signal printerChosen(var printer)
  signal manualSaved(string ip, string protocol)

  property string manualProtocol: "creality-ws"

  readonly property color fg: Color.popups.text
  readonly property color softText: Qt.rgba(fg.r, fg.g, fg.b, 0.72)

  spacing: 8

  Text {
    width: parent.width
    wrapMode: Text.WordWrap
    text: "Find your printer on the network. Make sure it is powered on and on the same Wi-Fi or LAN."
    color: root.softText
    font.family: root.fontFamily
    font.pixelSize: 11
  }

  ActionButton {
    label: root.searching ? "Searching…" : "Search network"
    enabled: !root.searching
    fontFamily: root.fontFamily
    onClicked: root.searchRequested()
  }

  Text {
    visible: !root.searching && root.found.length === 0
    width: parent.width
    wrapMode: Text.WordWrap
    text: "No printers found yet. You can enter the address below."
    color: root.softText
    font.family: root.fontFamily
    font.pixelSize: 10
  }

  Repeater {
    model: root.found

    delegate: Rectangle {
      id: foundRow

      required property var modelData

      width: root.width
      height: 40
      color: foundHover.hovered ? Qt.rgba(root.fg.r, root.fg.g, root.fg.b, 0.08) : "transparent"
      border.color: Color.popups.border
      border.width: 1

      HoverHandler { id: foundHover }

      Column {
        anchors.left: parent.left
        anchors.leftMargin: 8
        anchors.verticalCenter: parent.verticalCenter

        Text {
          text: (foundRow.modelData.model || "Printer") + "  ·  " + (foundRow.modelData.hostname || foundRow.modelData.ip)
          textFormat: Text.PlainText
          color: root.fg
          font.family: root.fontFamily
          font.pixelSize: 12
          font.bold: true
        }

        Text {
          text: foundRow.modelData.ip + "  ·  " + foundRow.modelData.protocol
          textFormat: Text.PlainText
          color: root.softText
          font.family: root.fontFamily
          font.pixelSize: 10
        }
      }

      MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: root.printerChosen(foundRow.modelData)
      }
    }
  }

  Text {
    text: "Or enter it manually"
    color: root.softText
    font.family: root.fontFamily
    font.pixelSize: 11
    font.bold: true
  }

  Row {
    width: parent.width
    spacing: 8

    Rectangle {
      width: parent.width - 8 - protocolButton.width
      height: 28
      color: "transparent"
      border.color: addressField.activeFocus ? Color.accent : Color.popups.border
      border.width: 1

      TapHandler {
        onTapped: addressField.forceActiveFocus()
      }

      TextInput {
        id: addressField
        anchors.fill: parent
        anchors.leftMargin: 8
        anchors.rightMargin: 8
        verticalAlignment: TextInput.AlignVCenter
        color: root.fg
        font.family: root.fontFamily
        font.pixelSize: 12
        clip: true
        selectByMouse: true
        selectionColor: Color.accent
        onAccepted: if (saveButton.enabled) saveButton.clicked()
      }

      Text {
        anchors.fill: parent
        anchors.leftMargin: 8
        verticalAlignment: Text.AlignVCenter
        visible: addressField.text.length === 0
        text: "192.168.1.50"
        color: root.softText
        font.family: root.fontFamily
        font.pixelSize: 12
      }
    }

    ActionButton {
      id: protocolButton
      label: root.manualProtocol === "creality-ws" ? "Creality OS" : "Moonraker"
      fontFamily: root.fontFamily
      onClicked: root.manualProtocol = root.manualProtocol === "creality-ws" ? "moonraker" : "creality-ws"
    }
  }

  ActionButton {
    id: saveButton
    label: "Save"
    enabled: Format.isValidAddress(addressField.text)
    fontFamily: root.fontFamily
    onClicked: root.manualSaved(addressField.text, root.manualProtocol)
  }
}
