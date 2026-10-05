import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons

Item {
  id: root

  property var bar
  property string moduleName
  property var settings

  readonly property string pluginDir: decodeURIComponent(Qt.resolvedUrl(".").toString().replace("file://", "")).replace(/\/$/, "")
  readonly property string bridgePath: pluginDir + "/bin/creality-bridge"
  readonly property string cacheDir: (Quickshell.env("XDG_CACHE_HOME") || (Quickshell.env("HOME") + "/.cache")) + "/omarchy-creality"

  readonly property bool vertical: bar ? bar.vertical : false
  implicitWidth: vertical ? (bar ? bar.barSize : 26) : row.implicitWidth + 14
  implicitHeight: vertical ? row.implicitHeight + 10 : (bar ? bar.barSize : 26)

  readonly property color iconColor: bar ? bar.barForeground : "white"

  property var status: ({ state: "offline", online: false, configured: true })
  property bool configured: true
  property double nowMs: Date.now()
  property var found: []
  property bool searching: false
  property bool searchedOnce: false
  property string frameSource: ""
  property int frameCounter: 0
  property int snapshotFailures: 0
  property string commandError: ""
  property bool installing: false


  readonly property string printState: status.state || "offline"
  readonly property bool isFinishedLit: printState === "finished"
    && (nowMs - (status.state_since || 0) * 1000) < (status.finished_lit_minutes || 10) * 60000
  readonly property bool isLit: printState === "printing" || printState === "paused" || printState === "preparing" || printState === "starting" || printState === "error" || isFinishedLit
  readonly property color markColor: printState === "error" ? Color.urgent : (isLit ? Color.accent : iconColor)
  readonly property var cameraInfo: status.camera || null
  readonly property bool isWebrtcCamera: !!cameraInfo && cameraInfo.kind === "webrtc"
  readonly property int cameraFailureLimit: 3
  readonly property string cameraState: {
    if (status.camera_state === "missing") return "missing"
    if (!cameraInfo) return "none"
    if (isWebrtcCamera) return status.camera_stream_url ? "stream" : "connecting"
    if (snapshotFailures >= cameraFailureLimit) return "none"
    return frameSource.length > 0 ? "ready" : "connecting"
  }
  readonly property bool showPercent: printState === "printing" || printState === "paused"

  function close() { popup.open = false }
  function open() {
    root.snapshotFailures = 0
    root.frameSource = ""
    popup.open = true
    snapshotTimer.restart()
    sendCameraKeepalive()
    refreshFrame()
  }
  function toggle() { if (popup.open) close(); else open() }
  function triggerPress(button) { root.toggle() }

  IpcHandler {
    target: "io.github.bbssyl.creality"
    function open(): void { root.open() }
    function close(): void { root.close() }
    function toggle(): void { root.toggle() }
  }

  function ingestLine(line) {
    var parsed = null
    try { parsed = JSON.parse(line) } catch (e) { return }
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) return
    root.configured = parsed.configured !== false
    root.status = parsed
    if (!root.configured && !root.searchedOnce) root.search()
  }

  function search() {
    root.searchedOnce = true
    if (discoverProc.running) return
    root.searching = true
    discoverProc.running = true
  }

  function ingestDiscovery(text) {
    var rows = []
    try { rows = JSON.parse(text || "[]") } catch (e) { rows = [] }
    if (!Array.isArray(rows)) rows = []
    root.found = rows
    root.searching = false
    if (rows.length === 1 && !root.configured) root.choose(rows[0])
  }

  function choose(printer) {
    saveConfig([
      "ip=" + printer.ip,
      "protocol=" + printer.protocol,
      "model=" + (printer.model || ""),
      "hostname=" + (printer.hostname || "")
    ])
  }

  function saveConfig(pairs) {
    configProc.command = ["/usr/bin/python3", root.bridgePath, "set-config"].concat(pairs)
    configProc.running = true
  }

  function sendCommand(action, argument) {
    if (commandProc.running) return
    root.commandError = ""
    var base = ["/usr/bin/python3", root.bridgePath, "cmd", action]
    commandProc.command = argument ? base.concat([argument]) : base
    commandProc.running = true
  }

  function ingestCommandResult(text) {
    var result = null
    try { result = JSON.parse(text) } catch (e) { result = null }
    if (result && result.ok === false) root.commandError = String(result.error || "unknown error")
  }

  readonly property bool cameraMissing: status.camera_state === "missing"

  onCameraMissingChanged: if (!cameraMissing) installing = false

  readonly property string installMarker: cacheDir + "/installing"
  readonly property bool installerSafe: installMarker.indexOf("'") < 0
  readonly property bool installerAvailable: status.camera_installer === true && installerSafe

  function installCameraSupport() {
    if (installProc.running || root.installing || !root.installerAvailable) return
    var marker = "'" + root.installMarker + "'"
    var script = "mkdir -p '" + root.cacheDir + "'; trap 'rm -f " + marker + "' EXIT; touch " + marker + "; omarchy pkg aur add go2rtc-bin"
    installProc.command = ["omarchy-launch-floating-terminal-with-presentation", script]
    root.installing = true
    installProc.running = true
    installGraceTimer.restart()
  }

  function finishInstallCheck(markerPresent) {
    if (!root.installing || installGraceTimer.running) return
    if (markerPresent) return
    root.installing = false
    root.sendCameraKeepalive()
  }

  function sendCameraKeepalive() {
    if (root.isWebrtcCamera && watchProc.running) watchProc.write("camera on\n")
  }

  function currentFrameUrl() {
    return root.isWebrtcCamera ? "" : (status.camera_url || "")
  }

  function refreshFrame() {
    var url = root.currentFrameUrl()
    if (!popup.open || snapshotProc.running || !url) return
    root.frameCounter = root.frameCounter + 1
    snapshotProc.pendingPath = root.cacheDir + "/frame-" + (root.frameCounter % 4) + ".jpg"
    snapshotProc.command = ["/usr/bin/python3", root.bridgePath, "snapshot", url, snapshotProc.pendingPath]
    snapshotProc.running = true
  }

  Process {
    id: watchProc
    command: ["/usr/bin/python3", root.bridgePath, "watch"]
    running: true
    stdinEnabled: true
    stdout: SplitParser {
      onRead: function(line) { root.ingestLine(line) }
    }
    onExited: function(code) { restartTimer.start() }
  }

  Timer {
    id: restartTimer
    interval: 3000
    onTriggered: watchProc.running = true
  }

  Process {
    id: discoverProc
    command: ["/usr/bin/python3", root.bridgePath, "discover"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.ingestDiscovery(text)
    }
    onExited: function(code) { root.searching = false }
  }

  Process {
    id: configProc
    onExited: function(code) {
      root.found = []
      watchProc.running = false
      restartTimer.start()
    }
  }

  Process {
    id: installProc
    onExited: function(code) { root.sendCameraKeepalive() }
  }

  Process {
    id: markerProc
    command: ["/usr/bin/test", "-e", root.installMarker]
    onExited: function(code) { root.finishInstallCheck(code === 0) }
  }

  Timer {
    id: installGraceTimer
    interval: 8000
  }

  Timer {
    interval: 2000
    repeat: true
    running: root.installing
    onTriggered: if (!markerProc.running) markerProc.running = true
  }

  Process {
    id: commandProc
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.ingestCommandResult(text)
    }
  }

  Process {
    id: snapshotProc
    property string pendingPath: ""
    onExited: function(code) {
      if (code !== 0) {
        root.snapshotFailures = root.snapshotFailures + 1
        return
      }
      root.snapshotFailures = 0
      root.frameSource = "file://" + pendingPath + "?" + root.frameCounter
    }
  }

  Connections {
    target: popup
    function onOpenChanged() {
      if (!popup.open && watchProc.running) watchProc.write("camera off\n")
    }
  }

  Timer {
    interval: 10000
    repeat: true
    running: popup.open && root.isWebrtcCamera
    onTriggered: root.sendCameraKeepalive()
  }

  Timer {
    id: snapshotTimer
    interval: 2000
    repeat: true
    running: popup.open
    onTriggered: root.refreshFrame()
  }

  Timer {
    interval: 30000
    repeat: true
    running: true
    onTriggered: root.nowMs = Date.now()
  }

  Grid {
    id: row
    anchors.centerIn: parent
    columns: root.vertical ? 1 : 2
    rowSpacing: 2
    columnSpacing: 4
    opacity: root.isLit ? 1.0 : 0.4

    PrinterMark {
      color: root.markColor
      unit: 14
    }

    Text {
      visible: root.showPercent
      text: (root.status.progress || 0) + "%"
      color: root.markColor
      font.family: bar ? bar.fontFamily : "monospace"
      font.pixelSize: 11
      font.bold: true
      horizontalAlignment: Text.AlignHCenter
    }
  }

  CrealityPanel {
    id: popup
    anchorItem: root
    bar: root.bar
    owner: root
    status: root.status
    configured: root.configured
    found: root.found
    searching: root.searching
    frameSource: root.frameSource
    cameraState: root.cameraState
    installerAvailable: root.installerAvailable
    installing: root.installing
    onInstallRequested: root.installCameraSupport()
    streamUrl: root.status.camera_stream_url || ""
    busy: commandProc.running
    commandError: root.commandError
    onSearchRequested: root.search()
    onPrinterChosen: function(printer) { root.choose(printer) }
    onManualSaved: function(ip, protocol) { root.saveConfig(["ip=" + ip, "protocol=" + protocol, "model=", "hostname="]) }
    onCommandRequested: function(action, argument) { root.sendCommand(action, argument) }
  }
}
