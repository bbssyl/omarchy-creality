# Changelog

## [1.1.0] - 2026-10-09

### Panel
- Job thumbnail: the sliced model preview is fetched and shown next to the filename in the panel (Creality OS `/downloads/humbnail/<name>.png`; Moonraker `/server/files/metadata` thumbnails, best-effort).

## [1.0.0] - 2026-10-05

Initial release.

### Printer status
- Automatic LAN discovery of Creality OS (WebSocket 9999) and Moonraker (7125) printers, with manual fallback.
- Automatic IP re-discovery by hostname when the saved address stops responding.
- States verified on a real K1 Max: `starting`, `preparing` (calibration, with `prep_step`), `printing`, `paused`, `stopping`, `finished`, `error`, `idle`, `offline`.

### Bar and panel
- Bar mark dimmed when idle, accent while printing or preparing with percent; a finished print stays lit (default 10 min).
- Panel with camera, state chip, progress, "Done at HH:MM", temperatures, Pause/Resume, Stop (in-panel confirmation) and light toggle.
- Pause/Stop hidden while the printer calibrates; indeterminate progress bar until printing starts.
- Panel is a layer-shell keyboard panel (KeyboardPanel): text fields take keyboard focus, Escape closes it.

### Camera
- Live WebRTC camera video (about 15 fps) via QtMultimedia over an on-demand, localhost-only go2rtc RTSP restream (K1 Max, K2, Hi).
- MJPEG snapshot cameras supported via the printer's snapshot URL.
- "Install camera support" button when go2rtc is missing: opens a visible terminal running `omarchy pkg aur add go2rtc-bin`; hidden on non-Omarchy systems, where the manual command is shown.

### Bridge
- Python 3 stdlib only, with its own RFC 6455 WebSocket client.
- Parent-death watchdog so the bridge and go2rtc never outlive the shell; every exit reason is logged to stderr.
- `watch` accepts `camera on` / `camera off` on stdin.
- Desktop notifications for finished, paused and error.
- Demo mode: `CREALITY_DEMO=1` or `bin/creality-bridge watch --demo`.
