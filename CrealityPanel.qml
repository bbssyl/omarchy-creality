import QtQuick
import qs.Commons
import qs.Ui

KeyboardPanel {
  id: root

  property var status: ({})
  property bool configured: true
  property var found: []
  property bool searching: false
  property string frameSource: ""
  property string cameraState: "none"
  property string streamUrl: ""
  property bool installerAvailable: false
  property bool installing: false
  property bool busy: false
  property string commandError: ""

  signal searchRequested()
  signal printerChosen(var printer)
  signal manualSaved(string ip, string protocol)
  signal commandRequested(string action, string argument)
  signal installRequested()

  property bool showSetup: false

  readonly property color fg: Color.popups.text
  readonly property color softText: Qt.rgba(fg.r, fg.g, fg.b, 0.72)
  readonly property string fontFamily: bar ? bar.fontFamily : "monospace"

  readonly property bool isOnline: status.online === true
  readonly property bool isSetupVisible: !configured || showSetup
  readonly property bool isDashboardVisible: !isSetupVisible && isOnline

  focusTarget: content
  padding: 12
  contentWidth: fittedContentWidth(380)
  contentHeight: fittedContentHeight(content.implicitHeight, 640)

  Column {
    id: content
    anchors.fill: parent
    focus: true
    spacing: 10

    Keys.onEscapePressed: root.close()

    Row {
      width: parent.width
      height: Math.max(titleColumn.implicitHeight, gearButton.height)

      Column {
        id: titleColumn
        width: parent.width - gearButton.width
        anchors.verticalCenter: parent.verticalCenter
        spacing: 1

        Text {
          width: parent.width
          text: root.isSetupVisible ? "Set up Creality" : ((root.status.model || "Creality") + (root.status.hostname ? "  ·  " + root.status.hostname : ""))
          textFormat: Text.PlainText
          color: root.fg
          font.family: root.fontFamily
          font.pixelSize: 14
          font.bold: true
          elide: Text.ElideRight
        }

        Text {
          visible: !root.isSetupVisible && !!root.status.ip
          width: parent.width
          text: root.status.ip || ""
          textFormat: Text.PlainText
          color: root.softText
          font.family: root.fontFamily
          font.pixelSize: 10
        }
      }

      Item {
        id: gearButton
        visible: root.configured
        width: 22
        height: 22
        anchors.verticalCenter: parent.verticalCenter

        Text {
          anchors.centerIn: parent
          text: root.showSetup ? "󰅖" : "󰒓"
          color: root.fg
          font.family: root.fontFamily
          font.pixelSize: 13
          opacity: gearArea.containsMouse ? 1 : 0.6
        }

        MouseArea {
          id: gearArea
          anchors.fill: parent
          hoverEnabled: true
          cursorShape: Qt.PointingHandCursor
          onClicked: root.showSetup = !root.showSetup
        }
      }
    }

    CameraView {
      visible: root.isDashboardVisible
      width: parent.width
      frameSource: root.frameSource
      cameraState: root.cameraState
      streamUrl: root.streamUrl
      active: root.open
      fontFamily: root.fontFamily
    }

    Rectangle {
      id: offlineSkeleton
      visible: !root.isSetupVisible && !root.isOnline
      width: parent.width
      height: 120
      color: "transparent"
      border.color: root.softText
      border.width: 1

      Rectangle {
        width: 22
        height: 22
        radius: 11
        anchors.horizontalCenter: parent.horizontalCenter
        y: 30
        color: "transparent"
        border.color: Color.accent
        border.width: 2

        Rectangle {
          width: 12
          height: 12
          color: Color.popups.background
          anchors.right: parent.right
          anchors.top: parent.top
          anchors.margins: -1
        }

        RotationAnimator on rotation {
          running: offlineSkeleton.visible && root.open
          from: 0
          to: 360
          duration: 1100
          loops: Animation.Infinite
        }
      }

      Text {
        anchors.horizontalCenter: parent.horizontalCenter
        y: 70
        text: "Looking for printer…"
        color: root.softText
        font.family: root.fontFamily
        font.pixelSize: 12
      }
    }

    JobSummary {
      visible: root.isDashboardVisible
      width: parent.width
      status: root.status
      fontFamily: root.fontFamily
    }

    TemperatureRow {
      visible: root.isDashboardVisible
      width: parent.width
      status: root.status
      fontFamily: root.fontFamily
    }

    ControlsBar {
      visible: root.isDashboardVisible
      width: parent.width
      status: root.status
      busy: root.busy
      commandError: root.commandError
      fontFamily: root.fontFamily
      onCommandRequested: function(action, argument) { root.commandRequested(action, argument) }
    }

    SetupView {
      visible: root.isSetupVisible
      width: parent.width
      found: root.found
      searching: root.searching
      fontFamily: root.fontFamily
      onSearchRequested: root.searchRequested()
      onPrinterChosen: function(printer) { root.showSetup = false; root.printerChosen(printer) }
      onManualSaved: function(ip, protocol) { root.showSetup = false; root.manualSaved(ip, protocol) }
    }
  }
}
