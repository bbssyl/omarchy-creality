import QtQuick
import qs.Commons

Column {
  id: root

  property string label: ""
  property string value: ""
  property real cellWidth: 100
  property string fontFamily: "monospace"

  readonly property color fg: Color.popups.text

  width: cellWidth
  spacing: 1

  Text {
    text: root.label
    color: Qt.rgba(root.fg.r, root.fg.g, root.fg.b, 0.72)
    font.family: root.fontFamily
    font.pixelSize: 10
  }

  Text {
    text: root.value
    color: root.fg
    font.family: root.fontFamily
    font.pixelSize: 13
    font.bold: true
  }
}
