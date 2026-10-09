import json
import urllib.error
import urllib.parse
import urllib.request

from .model import eta_from_remaining, number_or_none, offline_status

DEFAULT_PORT = 7125
POLL_SECONDS = 2.0
OBJECTS = "print_stats&virtual_sdcard&extruder&heater_bed&display_status&led"
STATE_MAP = {"standby": "idle", "printing": "printing", "paused": "paused", "complete": "finished", "cancelled": "idle", "error": "error"}


def http_json(url, timeout=3.0, data=None):
    request = urllib.request.Request(url, data=b"" if data else None, method="POST" if data else "GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode() or "{}")


def remaining_seconds(stats, progress):
    duration = number_or_none(stats.get("print_duration")) or 0
    if progress <= 0.01 or duration <= 0:
        return 0
    return int(duration / progress - duration)


def light_state(status, light_object):
    entry = status.get(light_object) if light_object else None
    color = entry.get("color_data") if isinstance(entry, dict) else None
    return None if not color else any(channel > 0 for channel in color[0])


def normalize(status, identity, config, webcam_url):
    stats = status.get("print_stats", {})
    state = STATE_MAP.get(stats.get("state"), "idle")
    progress = number_or_none(status.get("virtual_sdcard", {}).get("progress")) or 0
    remaining = remaining_seconds(stats, progress)
    extruder, bed = status.get("extruder", {}), status.get("heater_bed", {})
    message = stats.get("message")
    return {
        "online": True,
        "protocol": "moonraker",
        "model": config.get("model"),
        "hostname": identity.get("hostname") or config.get("hostname"),
        "ip": config["ip"],
        "state": state,
        "file": stats.get("filename") or None,
        "progress": int(round(progress * 100)),
        "elapsed_s": int(number_or_none(stats.get("print_duration")) or 0),
        "remaining_s": remaining,
        "eta_epoch": eta_from_remaining(remaining, state),
        "nozzle": {"cur": number_or_none(extruder.get("temperature")), "target": number_or_none(extruder.get("target"))},
        "bed": {"cur": number_or_none(bed.get("temperature")), "target": number_or_none(bed.get("target"))},
        "chamber": None,
        "light": light_state(status, config.get("light_object")),
        "error": {"code": "klipper", "message": message} if state == "error" and message else None,
        "camera_url": webcam_url,
        "camera": {"kind": "snapshot", "url": webcam_url} if webcam_url else None,
    }


class MoonrakerAdapter:
    def __init__(self, config):
        self.config = config
        self.base = f"http://{config['ip']}:{int(config.get('http_port') or DEFAULT_PORT)}"
        self.identity = {}
        self.webcam_url = None
        self.thumb_filename = None
        self.thumb_url = None

    def get(self, path):
        return http_json(self.base + path)

    def refresh_identity(self):
        self.identity = self.get("/printer/info").get("result", {})
        webcams = self.get("/server/webcams/list").get("result", {}).get("webcams", [])
        self.webcam_url = self.resolve_webcam(webcams)

    def resolve_webcam(self, webcams):
        for webcam in webcams:
            url = self.own_host_url(webcam.get("snapshot_url"))
            if url:
                return url
        return None

    def own_host_url(self, path):
        if not path or not isinstance(path, str):
            return None
        url = urllib.parse.urljoin(self.base + "/", path if path.startswith("http") else path.lstrip("/"))
        parsed = urllib.parse.urlparse(url)
        return url if parsed.scheme in ("http", "https") and parsed.hostname == self.config["ip"] else None

    def resolve_thumbnail(self, filename):
        if not filename:
            self.thumb_filename, self.thumb_url = None, None
            return None
        if filename == self.thumb_filename:
            return self.thumb_url
        self.thumb_filename, self.thumb_url = filename, None
        try:
            meta = self.get(f"/server/files/metadata?filename={urllib.parse.quote(filename)}")["result"]
            thumbs = meta.get("thumbnails") or []
            best = max(thumbs, key=lambda thumb: thumb.get("size") or 0, default=None)
            relative = best.get("relative_path") if best else None
            if relative:
                directory = filename.rsplit("/", 1)[0] if "/" in filename else ""
                full_path = f"{directory}/{relative}" if directory else relative
                self.thumb_url = f"{self.base}/server/files/gcodes/{urllib.parse.quote(full_path)}"
        except Exception:
            pass
        return self.thumb_url

    def status(self):
        if not self.identity:
            self.refresh_identity()
        result = self.get(f"/printer/objects/query?{OBJECTS}")["result"]["status"]
        normalized = normalize(result, self.identity, self.config, self.webcam_url)
        normalized["thumbnail_url"] = self.resolve_thumbnail(normalized["file"])
        return normalized

    def fetch_once(self):
        return self.status()

    def run(self, on_update, stop):
        failures = 0
        while not stop.is_set():
            try:
                on_update(self.status())
                failures = 0
            except Exception:
                self.identity = {}
                failures += 1
                on_update(offline_status(self.config))
            stop.wait(min(POLL_SECONDS * 2 ** min(failures, 4), 30.0))

    def command(self, action, argument=None):
        if action in ("pause", "resume"):
            http_json(f"{self.base}/printer/print/{action}", data=True)
        elif action == "stop":
            http_json(f"{self.base}/printer/print/cancel", data=True)
        elif action == "light" and self.config.get("light_macro"):
            script = urllib.parse.quote(f"{self.config['light_macro']} STATE={1 if argument == 'on' else 0}")
            http_json(f"{self.base}/printer/gcode/script?script={script}", data=True)
        else:
            raise ValueError(f"unsupported command: {action}")
