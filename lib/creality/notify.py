import subprocess

APP_NAME = "Creality"


def describe(previous, current, hostname):
    name = hostname or "Printer"
    file_name = current.get("file") or "print"
    if current["state"] == "finished" and previous in ("printing", "paused"):
        return "Print finished", f"{name}: {file_name} is done"
    if current["state"] == "error" and previous != "error":
        error = current.get("error") or {}
        return "Printer error", f"{name}: {error.get('message') or 'attention needed'}"
    if current["state"] == "paused" and previous == "printing":
        return "Print paused", f"{name}: {file_name} is paused"
    return None


class Notifier:
    def __init__(self, enabled):
        self.enabled = enabled
        self.previous = None

    def observe(self, status):
        state = status["state"]
        if state == "offline" or state == self.previous:
            return
        message = describe(self.previous, status, status.get("hostname")) if self.previous else None
        self.previous = state
        if message and self.enabled:
            send(*message, urgent=state == "error")


def send(title, body, urgent=False):
    level = "critical" if urgent else "normal"
    try:
        subprocess.run(["notify-send", "-a", APP_NAME, "-u", level, title, body], timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return
