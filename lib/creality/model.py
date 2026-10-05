import math
import time

STATES = ("idle", "preparing", "starting", "stopping", "printing", "paused", "finished", "error", "offline")


def offline_status(config):
    return {
        "online": False,
        "protocol": config.get("protocol"),
        "model": config.get("model"),
        "hostname": config.get("hostname"),
        "ip": config.get("ip"),
        "state": "offline",
        "prep_step": None,
        "file": None,
        "progress": 0,
        "elapsed_s": 0,
        "remaining_s": 0,
        "eta_epoch": None,
        "nozzle": {"cur": None, "target": None},
        "bed": {"cur": None, "target": None},
        "chamber": None,
        "light": None,
        "error": None,
        "camera_url": None,
        "camera": None,
    }


def eta_from_remaining(remaining_s, state):
    if state not in ("printing", "paused") or not remaining_s:
        return None
    return int(time.time() + remaining_s)


def number_or_none(value):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return round(number, 1) if math.isfinite(number) else None


def public_view(status):
    return {key: value for key, value in status.items() if not key.startswith("_")}
