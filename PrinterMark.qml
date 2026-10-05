import QtQuick

Item {
  id: root

  property color color: "white"
  property real unit: 14

  implicitWidth: unit
  implicitHeight: unit

  Rectangle {
    x: root.unit * 0.1
    y: root.unit * 0.05
    width: root.unit * 0.8
    height: root.unit * 0.8
    color: "transparent"
    border.color: root.color
    border.width: Math.max(1, Math.round(root.unit * 0.12))
  }

  Rectangle {
    x: root.unit * 0.38
    y: root.unit * 0.3
    width: root.unit * 0.24
    height: root.unit * 0.24
    color: root.color
  }

  Rectangle {
    x: root.unit * 0.2
    y: root.unit * 0.8
    width: root.unit * 0.6
    height: Math.max(1, Math.round(root.unit * 0.12))
    color: root.color
  }
}
