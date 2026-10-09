import time

from .model import eta_from_remaining

TOTAL_SECONDS = 5400
STEP_SECONDS = 2.0


def frame(progress, light):
    state = "finished" if progress >= 100 else "printing"
    remaining = int(TOTAL_SECONDS * (100 - progress) / 100)
    heating = state == "printing"
    return {
        "online": True, "protocol": "demo", "model": "K1C", "hostname": "K1C-Demo",
        "ip": "192.168.1.50", "state": state, "file": "benchy_0.2mm_PLA.gcode",
        "progress": progress, "elapsed_s": TOTAL_SECONDS - remaining, "remaining_s": remaining,
        "eta_epoch": eta_from_remaining(remaining, state),
        "nozzle": {"cur": 218.4 if heating else 41.0, "target": 220.0 if heating else 0.0},
        "bed": {"cur": 60.1 if heating else 33.0, "target": 60.0 if heating else 0.0},
        "chamber": {"cur": 34.0}, "light": light, "error": None, "camera_url": None, "camera": None,
        "thumbnail_url": None,
    }


class DemoAdapter:
    def __init__(self, config):
        self.config = config
        self.light = True
        self.progress = 37

    def status(self):
        return frame(self.progress, self.light)

    def fetch_once(self):
        return self.status()

    def run(self, on_update, stop):
        while not stop.is_set():
            on_update(self.status())
            self.progress = 0 if self.progress >= 100 else min(100, self.progress + 1)
            stop.wait(STEP_SECONDS)

    def command(self, action, argument=None):
        if action == "light":
            self.light = argument == "on"
