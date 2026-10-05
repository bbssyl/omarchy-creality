.pragma library

function pad(value) {
  return value < 10 ? "0" + value : String(value)
}

function clock(epoch) {
  if (!epoch) return "--:--"
  var date = new Date(epoch * 1000)
  return pad(date.getHours()) + ":" + pad(date.getMinutes())
}

function duration(seconds) {
  var total = Math.max(0, Math.round(seconds || 0))
  var hours = Math.floor(total / 3600)
  var minutes = Math.floor((total % 3600) / 60)
  return hours > 0 ? hours + "h " + pad(minutes) + "m" : minutes + "m"
}

function temperature(entry) {
  if (!entry || entry.cur === null || entry.cur === undefined) return "--"
  var target = entry.target ? " / " + Math.round(entry.target) : ""
  return Math.round(entry.cur) + target + "°"
}

function stateLabel(state) {
  var labels = { idle: "Idle", preparing: "Preparing", starting: "Starting", stopping: "Stopping", printing: "Printing", paused: "Paused", finished: "Finished", error: "Error", offline: "Offline" }
  return labels[state] || state
}

function isValidAddress(text) {
  return /^[0-9]{1,3}(\.[0-9]{1,3}){3}$/.test(text)
}

function subLabel(state) {
  var labels = { preparing: "Calibrating…", starting: "Starting…", stopping: "Stopping…" }
  return labels[state] || ""
}
