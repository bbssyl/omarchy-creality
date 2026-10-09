import QtQuick
import qs.Commons
import "Format.js" as Format

Row {
  id: root

  property var status: ({})
  property string thumbnailSource: ""
  property string fontFamily: "monospace"

  readonly property color fg: Color.popups.text
  readonly property color softText: Qt.rgba(fg.r, fg.g, fg.b, 0.72)
  readonly property string printState: status.state || "offline"
  readonly property bool isActive: printState === "printing" || printState === "paused"
  readonly property bool isTransition: printState === "preparing" || printState === "starting" || printState === "stopping"
  readonly property bool hasEstimate: isActive && (status.remaining_s || 0) > 0
  readonly property color stateColor: printState === "error" ? Color.urgent : (printState === "printing" || printState === "finished" || printState === "preparing" || printState === "starting" ? Color.accent : softText)

  spacing: 10

  Rectangle {
    id: thumb
    visible: root.thumbnailSource.length > 0
    width: visible ? 56 : 0
    height: 56
    color: Qt.rgba(root.fg.r, root.fg.g, root.fg.b, 0.08)
    border.color: Qt.rgba(root.fg.r, root.fg.g, root.fg.b, 0.2)
    border.width: 1
    clip: true

    Image {
      anchors.fill: parent
      anchors.margins: 3
      source: root.thumbnailSource
      fillMode: Image.PreserveAspectFit
      cache: false
      asynchronous: true
    }
  }

  Column {
    id: info
    width: parent.width - thumb.width - (thumb.visible ? root.spacing : 0)
    spacing: 6

    Row {
      width: parent.width
      spacing: 8

      Text {
        width: parent.width - chip.width - 8
        anchors.verticalCenter: parent.verticalCenter
        text: root.status.file || "No active job"
        textFormat: Text.PlainText
        color: root.fg
        font.family: root.fontFamily
        font.pixelSize: 12
        font.bold: true
        elide: Text.ElideMiddle
      }

      Rectangle {
        id: chip
        width: chipText.implicitWidth + 16
        height: 20
        radius: 10
        anchors.verticalCenter: parent.verticalCenter
        color: "transparent"
        border.color: root.stateColor
        border.width: 1

        Text {
          id: chipText
          anchors.centerIn: parent
          text: Format.stateLabel(root.printState)
          color: root.stateColor
          font.family: root.fontFamily
          font.pixelSize: 10
          font.bold: true
        }
      }
    }

    Rectangle {
      id: track
      width: parent.width
      height: 8
      color: Qt.rgba(root.fg.r, root.fg.g, root.fg.b, 0.08)
      clip: true

      Rectangle {
        visible: !root.isTransition
        width: parent.width * Math.max(0, Math.min(100, root.status.progress || 0)) / 100
        height: parent.height
        color: root.printState === "error" ? Color.urgent : Color.accent
      }

      Rectangle {
        id: sweep
        visible: root.isTransition
        width: track.width / 4
        height: parent.height
        color: root.printState === "stopping" ? root.softText : Color.accent

        SequentialAnimation on x {
          running: sweep.visible
          loops: Animation.Infinite
          NumberAnimation { from: -sweep.width; to: track.width; duration: 1400; easing.type: Easing.InOutQuad }
        }
      }
    }

    Row {
      width: parent.width

      Text {
        width: parent.width / 2
        text: root.hasEstimate ? "Done at " + Format.clock(root.status.eta_epoch) : (root.printState === "finished" ? "Done" : Format.subLabel(root.printState))
        color: root.fg
        font.family: root.fontFamily
        font.pixelSize: 12
        font.bold: true
      }

      Text {
        width: parent.width / 2
        horizontalAlignment: Text.AlignRight
        text: root.isTransition ? "" : (root.status.progress || 0) + "%" + (root.hasEstimate ? "  ·  " + Format.duration(root.status.remaining_s) + " left" : "")
        color: root.softText
        font.family: root.fontFamily
        font.pixelSize: 11
      }
    }

    Text {
      visible: root.printState === "error" && !!root.status.error
      width: parent.width
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: root.status.error ? root.status.error.message + " (" + root.status.error.code + ")" : ""
      color: Color.urgent
      font.family: root.fontFamily
      font.pixelSize: 11
    }
  }
}
