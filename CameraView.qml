import QtQuick
import QtMultimedia
import qs.Commons

Rectangle {
  id: root

  property string frameSource: ""
  property string streamUrl: ""
  property string cameraState: "none"
  property bool active: false
  property bool installerAvailable: false
  property bool installing: false
  property string fontFamily: "monospace"

  readonly property color fg: Color.popups.text
  readonly property bool useStream: streamUrl.length > 0
  readonly property bool showVideo: useStream && hasVideo && active
  readonly property bool showFrame: !useStream && frameSource.length > 0 && cameraState === "ready"
  readonly property string messageKey: {
    if (cameraState === "missing") return "missing"
    if (cameraState === "none" || gaveUp) return "none"
    return "connecting"
  }
  signal installRequested()

  readonly property bool showInstall: messageKey === "missing" && !showVideo && !showFrame
  readonly property var messages: ({
    connecting: "Connecting camera…",
    missing: "Live camera needs go2rtc. Install it with: yay -S go2rtc-bin",
    none: "No camera"
  })

  property bool hasVideo: false
  property bool gaveUp: false
  property int retryDelayMs: 1000

  property bool retrying: false
  readonly property bool wantPlay: active && useStream && !retrying

  onWantPlayChanged: {
    root.hasVideo = false
    if (wantPlay) {
      root.gaveUp = false
      giveUpTimer.restart()
    } else {
      giveUpTimer.stop()
    }
  }

  height: Math.round(width * 9 / 16)
  color: Qt.rgba(fg.r, fg.g, fg.b, 0.08)
  border.color: Color.popups.border
  border.width: 1
  clip: true

  MediaPlayer {
    id: player
    source: root.wantPlay ? root.streamUrl : ""
    videoOutput: video
    onSourceChanged: if (source.toString().length > 0) play()
    playbackOptions.playbackIntent: PlaybackOptions.LowLatencyStreaming
    onErrorOccurred: function(error, message) {
      root.hasVideo = false
      root.retrying = true
      retryTimer.interval = root.retryDelayMs
      root.retryDelayMs = Math.min(root.retryDelayMs * 2, 8000)
      retryTimer.restart()
    }
  }

  VideoOutput {
    id: video
    anchors.fill: parent
    fillMode: VideoOutput.PreserveAspectCrop
  }

  Connections {
    target: video.videoSink

    function onVideoFrameChanged() {
      if (root.hasVideo) return
      root.hasVideo = true
      root.retryDelayMs = 1000
      giveUpTimer.stop()
    }
  }

  Timer {
    id: retryTimer
    onTriggered: root.retrying = false
  }

  Timer {
    id: giveUpTimer
    interval: 20000
    onTriggered: root.gaveUp = true
  }

  Image {
    anchors.fill: parent
    source: root.showFrame ? root.frameSource : ""
    cache: false
    asynchronous: true
    fillMode: Image.PreserveAspectCrop
    visible: status === Image.Ready
  }

  Column {
    anchors.centerIn: parent
    width: parent.width - 24
    spacing: 10
    visible: root.showInstall && root.installerAvailable

    Text {
      width: parent.width
      horizontalAlignment: Text.AlignHCenter
      wrapMode: Text.WordWrap
      text: root.installing ? "Installing camera support…" : "Live camera needs go2rtc"
      color: Qt.rgba(root.fg.r, root.fg.g, root.fg.b, 0.72)
      font.family: root.fontFamily
      font.pixelSize: 11
    }

    ActionButton {
      anchors.horizontalCenter: parent.horizontalCenter
      enabled: !root.installing
      label: root.installing ? "Installing…" : "Install camera support"
      fontFamily: root.fontFamily
      onClicked: root.installRequested()
    }
  }

  Text {
    anchors.centerIn: parent
    width: parent.width - 24
    visible: !root.showVideo && !root.showFrame && !(root.showInstall && root.installerAvailable)
    horizontalAlignment: Text.AlignHCenter
    wrapMode: Text.WordWrap
    textFormat: Text.PlainText
    text: root.messages[root.messageKey]
    color: Qt.rgba(root.fg.r, root.fg.g, root.fg.b, 0.72)
    font.family: root.fontFamily
    font.pixelSize: 11
  }
}
