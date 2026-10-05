import atexit
import json
import sys
import threading
import time

from . import config as config_store
from .discovery import discover, match_by_hostname
from .net import port_open
from .camera import CameraBridge
from .lifecycle import log, write_line
from .model import offline_status, public_view
from .notify import Notifier

REDISCOVER_AFTER_SECONDS = 20
REDISCOVER_SCHEDULE_SECONDS = (60, 120, 300, 900, 1800)


def comparable(status):
    trimmed = {key: value for key, value in status.items() if key != "eta_epoch"}
    trimmed["eta_minute"] = (status.get("eta_epoch") or 0) // 60
    return json.dumps(trimmed, sort_keys=True)


class Watcher:
    def __init__(self, config, build_adapter, config_file=None):
        self.config = config
        self.build_adapter = build_adapter
        self.config_file = config_file
        self.notifier = Notifier(config.get("notify", True))
        self.last_line = None
        self.state_since = time.time()
        self.last_state = None
        self.offline_since = None
        self.last_rediscovery = 0.0
        self.generation = 0
        self.rediscover_attempts = 0
        self.rediscovering = False
        self.restart = threading.Event()
        self.lock = threading.Lock()
        self.camera = CameraBridge()
        self.last_status = None
        self.camera_info = {}

    def emit(self, status, force=False):
        with self.lock:
            self.last_status = status
            if status["state"] != self.last_state:
                self.last_state, self.state_since = status["state"], time.time()
            view = {**public_view(status), "configured": True, "state_since": int(self.state_since),
                    "finished_lit_minutes": self.config.get("finished_lit_minutes", 10),
                    **self.camera.info()}
            line = comparable(view)
            if force or line != self.last_line:
                self.last_line = line
                write_line(view)

    def camera_source(self):
        camera = (self.last_status or {}).get("camera") or {}
        return camera.get("source") if camera.get("kind") == "webrtc" else None

    def handle_camera_request(self, wanted):
        source = self.camera_source()
        if wanted and source:
            self.camera.request(source)
        elif not wanted:
            self.camera.stop()
        if self.last_status:
            self.emit(self.last_status)

    def read_commands(self):
        for line in sys.stdin:
            command = line.strip()
            if command in ("camera on", "camera off"):
                self.handle_camera_request(command == "camera on")
        log("stdin closed; continuing without camera control")

    def supervise_camera(self):
        while True:
            time.sleep(2)
            self.camera.reap_idle()
            if self.last_status:
                self.emit(self.last_status)

    def handle_update(self, generation, status):
        if generation != self.generation:
            return
        self.notifier.observe(status)
        self.emit(status)
        if status["online"]:
            self.offline_since = None
            self.rediscover_attempts = 0
        elif self.offline_since is None:
            self.offline_since = time.time()
        self.maybe_rediscover()

    def next_rediscovery_delay(self):
        index = min(self.rediscover_attempts, len(REDISCOVER_SCHEDULE_SECONDS) - 1)
        return REDISCOVER_SCHEDULE_SECONDS[index]

    def maybe_rediscover(self):
        now = time.time()
        if self.offline_since is None or not self.config.get("hostname") or self.rediscovering:
            return
        if now - self.offline_since < REDISCOVER_AFTER_SECONDS:
            return
        if now - self.last_rediscovery < self.next_rediscovery_delay():
            return
        self.last_rediscovery = now
        self.rediscovering = True
        threading.Thread(target=self.rediscover, daemon=True).start()

    def configured_port(self):
        ws_port, http_port = self.discovery_ports()
        return http_port if self.config.get("protocol") == "moonraker" else ws_port

    def rediscover(self):
        try:
            if port_open(self.config.get("ip"), self.configured_port()):
                return
            self.rediscover_attempts += 1
            found = match_by_hostname(discover(None, *self.discovery_ports()), self.config.get("hostname"))
            if found and found["ip"] != self.config.get("ip"):
                self.adopt_address(found["ip"])
        finally:
            self.rediscovering = False

    def adopt_address(self, address):
        config_store.update_address(address, self.config_file)
        self.config["ip"] = address
        self.restart.set()

    def discovery_ports(self):
        return int(self.config.get("ws_port") or 9999), int(self.config.get("http_port") or 7125)

    def run(self):
        atexit.register(self.camera.stop)
        threading.Thread(target=self.read_commands, daemon=True).start()
        threading.Thread(target=self.supervise_camera, daemon=True).start()
        while True:
            stop = threading.Event()
            self.generation += 1
            generation = self.generation
            adapter = self.build_adapter(self.config)
            worker = threading.Thread(
                target=adapter.run,
                args=(lambda status: self.handle_update(generation, status), stop),
                daemon=True,
            )
            worker.start()
            self.restart.wait()
            self.restart.clear()
            stop.set()
            worker.join(timeout=3)


def emit_unconfigured():
    write_line({**offline_status({}), "configured": False})
