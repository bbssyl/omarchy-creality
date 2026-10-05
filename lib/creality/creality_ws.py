import json
import socket
import time

from .net import port_open
from .model import eta_from_remaining, number_or_none, offline_status
from .wsclient import WebSocketClient, WebSocketError

DEFAULT_WS_PORT = 9999
DEFAULT_CAMERA_PORT = 8080
REQUEST_STATUS = {"method": "get", "params": {"ReqPrinterPara": 1}}
REFRESH_SECONDS = 8
STATE_PRINTING, STATE_STOPPED, STATE_PAUSED = 1, 4, 5
STATE_TRANSITIONS = {7: "stopping", 9: "starting"}
MAX_BACKOFF_SECONDS = 15.0
WEBRTC_PORT = 8000
WEBRTC_SOURCE = "webrtc:http://{host}:" + str(WEBRTC_PORT) + "/call/webrtc_local#format=creality"


def error_code(raw):
    error = raw.get("err")
    code = error.get("errcode") if isinstance(error, dict) else error
    return int(number_or_none(code) or 0)


def has_job(raw):
    return bool(raw.get("printFileName"))


SELF_TEST_DONE = 100


def is_calibrating(raw, code):
    if not (code == STATE_PRINTING or (code == 0 and has_job(raw))):
        return False
    step = number_or_none(raw.get("withSelfTest"))
    enabled = number_or_none(raw.get("enableSelfTest")) == 1
    return enabled and step is not None and 0 <= step < SELF_TEST_DONE


def derive_state(raw):
    code = int(number_or_none(raw.get("state")) or 0)
    progress = number_or_none(raw.get("printProgress")) or 0
    if error_code(raw) != 0:
        return "error"
    if code == STATE_PAUSED or number_or_none(raw.get("pause")) == 1:
        return "paused"
    if code in STATE_TRANSITIONS:
        return STATE_TRANSITIONS[code]
    if has_job(raw) and progress >= 100:
        return "finished"
    if code == STATE_STOPPED:
        return "idle"
    if is_calibrating(raw, code):
        return "preparing"
    return "printing" if code == STATE_PRINTING or (code == 0 and has_job(raw)) else "idle"


def error_info(raw):
    if error_code(raw) == 0:
        return None
    error = raw.get("err")
    key = error.get("key") if isinstance(error, dict) else None
    return {"code": str(error_code(raw)), "message": str(key or "printer error")}


def base_name(path):
    return str(path).replace("\\", "/").split("/")[-1] if path else None


def camera_url(raw, host, camera_port):
    if number_or_none(raw.get("webrtcSupport")) == 1:
        return None
    return f"http://{host}:{camera_port}/?action=snapshot"


def prep_step(raw, state):
    return int(number_or_none(raw.get("withSelfTest")) or 0) if state == "preparing" else None


def camera_descriptor(raw, host, camera_port, webrtc_forced):
    if number_or_none(raw.get("webrtcSupport")) == 1 or webrtc_forced:
        return {"kind": "webrtc", "source": WEBRTC_SOURCE.format(host=host)}
    return {"kind": "snapshot", "url": f"http://{host}:{camera_port}/?action=snapshot"}


def normalize(raw, host, camera_port=DEFAULT_CAMERA_PORT, webrtc_forced=False):
    state = derive_state(raw)
    remaining = int(number_or_none(raw.get("printLeftTime")) or 0)
    chamber = number_or_none(raw.get("boxTemp"))
    light = raw.get("lightSw")
    return {
        "online": True,
        "protocol": "creality-ws",
        "model": raw.get("model") or raw.get("modelVersion"),
        "hostname": raw.get("hostname"),
        "ip": host,
        "state": state,
        "prep_step": prep_step(raw, state),
        "file": base_name(raw.get("printFileName")),
        "progress": int(number_or_none(raw.get("printProgress")) or 0),
        "elapsed_s": int(number_or_none(raw.get("printJobTime")) or 0),
        "remaining_s": remaining,
        "eta_epoch": eta_from_remaining(remaining, state),
        "nozzle": {"cur": number_or_none(raw.get("nozzleTemp")), "target": number_or_none(raw.get("targetNozzleTemp"))},
        "bed": {"cur": number_or_none(raw.get("bedTemp0")), "target": number_or_none(raw.get("targetBedTemp0"))},
        "chamber": None if chamber is None else {"cur": chamber},
        "light": None if light is None else bool(int(number_or_none(light) or 0)),
        "error": error_info(raw),
        "camera_url": camera_url(raw, host, camera_port) if not webrtc_forced else None,
        "camera": camera_descriptor(raw, host, camera_port, webrtc_forced),
    }


class CrealityWsAdapter:
    def __init__(self, config):
        self.config = config
        self.host = config["ip"]
        self.port = int(config.get("ws_port") or DEFAULT_WS_PORT)
        self.camera_port = int(config.get("camera_port") or DEFAULT_CAMERA_PORT)
        self.raw = {}
        self.backoff = 1.0
        self.snapshot_port_closed = None

    def status(self):
        return normalize(self.raw, self.host, self.camera_port, self.webrtc_forced())

    def webrtc_forced(self):
        if self.snapshot_port_closed is None:
            self.snapshot_port_closed = (
                not port_open(self.host, self.camera_port) and port_open(self.host, WEBRTC_PORT)
            )
        return self.snapshot_port_closed

    def open(self, timeout=5.0):
        client = WebSocketClient(self.host, self.port, timeout)
        client.connect()
        client.send_text(json.dumps(REQUEST_STATUS))
        return client

    def handle_message(self, client, message):
        if not isinstance(message, str):
            return False
        try:
            payload = json.loads(message)
        except ValueError:
            return False
        if not isinstance(payload, dict):
            return False
        if payload.get("ModeCode") == "heart_beat":
            client.send_text("ok")
            return False
        self.raw.update(payload)
        return True

    def poll(self, client, on_update, stop):
        next_request = time.monotonic() + REFRESH_SECONDS
        client.sock.settimeout(1.0)
        quiet_since = time.monotonic()
        while not stop.is_set():
            try:
                changed = self.handle_message(client, client.receive())
                quiet_since = time.monotonic()
                if changed:
                    self.backoff = 1.0
                    on_update(self.status())
            except socket.timeout:
                if time.monotonic() - quiet_since > REFRESH_SECONDS * 4:
                    raise WebSocketError("printer went silent")
            if time.monotonic() >= next_request:
                client.send_text(json.dumps(REQUEST_STATUS))
                next_request = time.monotonic() + REFRESH_SECONDS

    def run(self, on_update, stop):
        self.backoff = 1.0
        while not stop.is_set():
            client = None
            try:
                client = self.open()
                self.poll(client, on_update, stop)
            except Exception:
                on_update(offline_status(self.config))
                stop.wait(self.backoff)
                self.backoff = min(self.backoff * 2, MAX_BACKOFF_SECONDS)
            finally:
                if client:
                    client.close()

    def fetch_once(self, wait=4.0):
        self.raw = {}
        client = self.open()
        client.sock.settimeout(1.0)
        deadline = time.monotonic() + wait
        try:
            while time.monotonic() < deadline and "nozzleTemp" not in self.raw:
                try:
                    self.handle_message(client, client.receive(deadline))
                except socket.timeout:
                    continue
        finally:
            client.close()
        return self.status()

    def command(self, action, argument=None):
        params = {
            "pause": {"pause": 1},
            "resume": {"pause": 0},
            "stop": {"stop": 1},
            "light": {"lightSw": 1 if argument == "on" else 0},
        }.get(action)
        if params is None:
            raise ValueError(f"unknown command: {action}")
        client = self.open()
        try:
            client.send_text(json.dumps({"method": "set", "params": params}))
            time.sleep(0.3)
        finally:
            client.close()
