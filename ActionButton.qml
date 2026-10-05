import QtQuick
import qs.Commons

Rectangle {
  id: root

  property string label: ""
  property bool danger: false
  property string fontFamily: "monospace"

  signal clicked()

  readonly property color fg: Color.popups.text

  width: buttonText.implicitWidth + 24
  height: 28
  opacity: enabled ? 1 : 0.4
  color: buttonHover.hovered && enabled ? Qt.rgba(fg.r, fg.g, fg.b, 0.1) : "transparent"
  border.color: danger ? Color.urgent : Color.popups.border
  border.width: 1

  HoverHandler { id: buttonHover }

  Text {
    id: buttonText
    anchors.centerIn: parent
    text: root.label
    color: root.danger ? Color.urgent : root.fg
    font.family: root.fontFamily
    font.pixelSize: 11
    font.bold: true
  }

  MouseArea {
    anchors.fill: parent
    cursorShape: Qt.PointingHandCursor
    onClicked: if (root.enabled) root.clicked()
  }
}
