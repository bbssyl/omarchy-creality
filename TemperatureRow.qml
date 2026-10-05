import QtQuick
import "Format.js" as Format

Row {
  id: root

  property var status: ({})
  property string fontFamily: "monospace"

  readonly property int cellCount: status.chamber ? 3 : 2

  TempCell {
    label: "Nozzle"
    value: Format.temperature(root.status.nozzle)
    cellWidth: root.width / root.cellCount
    fontFamily: root.fontFamily
  }

  TempCell {
    label: "Bed"
    value: Format.temperature(root.status.bed)
    cellWidth: root.width / root.cellCount
    fontFamily: root.fontFamily
  }

  TempCell {
    visible: !!root.status.chamber
    label: "Chamber"
    value: root.status.chamber ? Format.temperature(root.status.chamber) : ""
    cellWidth: root.width / root.cellCount
    fontFamily: root.fontFamily
  }
}
