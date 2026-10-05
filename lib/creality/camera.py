import ctypes
import json
import shutil
import signal
import socket
import subprocess
import threading
import time

from .net import port_open

STREAM_NAME = "printer"
LIVE_NAME = "live"
RETIMER_COMMAND = (
    "exec:ffmpeg -hide_banner -loglevel error -use_wallclock_as_timestamps 1 -fflags nobuffer "
    "-rtsp_transport tcp -i rtsp://127.0.0.1:{rtsp_port}/{stream} -c copy -f rtsp {{output}}"
)
IDLE_SECONDS = 30.0
STOP_WAIT_SECONDS = 3.0
PR_SET_PDEATHSIG = 1


def die_with_parent():
    try:
        ctypes.CDLL(None).prctl(PR_SET_PDEATHSIG, signal.SIGTERM)
    except Exception:
        return


def free_ports(count):
    probes = [socket.socket() for _ in range(count)]
    try:
        for probe in probes:
            probe.bind(("127.0.0.1", 0))
        return [probe.getsockname()[1] for probe in probes]
    finally:
        for probe in probes:
            probe.close()


def inline_config(port, rtsp_port, source):
    return json.dumps({
        "api": {"listen": f"127.0.0.1:{port}", "origin": ""},
        "rtsp": {"listen": f"127.0.0.1:{rtsp_port}"},
        "rtmp": {"listen": ""},
        "webrtc": {"listen": ""},
        "srtp": {"listen": ""},
        "streams": {
            STREAM_NAME: source,
            LIVE_NAME: RETIMER_COMMAND.format(rtsp_port=rtsp_port, stream=STREAM_NAME),
        },
    })


def installer_available():
    return all(shutil.which(name) for name in ("omarchy", "omarchy-launch-floating-terminal-with-presentation"))


class CameraBridge:
    def __init__(self):
        self.process = None
        self.port = None
        self.rtsp_port = None
        self.source = None
        self.last_request = 0.0
        self.missing = False
        self.lock = threading.Lock()

    def request(self, source):
        with self.lock:
            self.last_request = time.monotonic()
            if self.process is not None and (self.process.poll() is not None or self.source != source):
                self.stop_locked()
            if self.process is None:
                self.start_locked(source)

    def start_locked(self, source):
        binary = shutil.which("go2rtc")
        self.missing = binary is None
        if self.missing:
            return
        port, rtsp_port = free_ports(2)
        self.process = subprocess.Popen(
            [binary, "-config", inline_config(port, rtsp_port, source)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            preexec_fn=die_with_parent,
        )
        self.port, self.rtsp_port, self.source = port, rtsp_port, source

    def stop(self):
        with self.lock:
            self.stop_locked()

    def stop_locked(self):
        process, self.process = self.process, None
        self.port = self.rtsp_port = self.source = None
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(STOP_WAIT_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(STOP_WAIT_SECONDS)

    def reap_idle(self):
        with self.lock:
            if self.process is not None and time.monotonic() - self.last_request > IDLE_SECONDS:
                self.stop_locked()

    def info(self):
        with self.lock:
            if self.missing and self.process is None:
                return {"camera_state": "missing", "camera_frame_url": None, "camera_stream_url": None,
                        "camera_installer": installer_available()}
            if self.process is None or self.process.poll() is not None:
                return {"camera_state": "off", "camera_frame_url": None, "camera_stream_url": None}
            if not (port_open("127.0.0.1", self.port) and port_open("127.0.0.1", self.rtsp_port)):
                return {"camera_state": "starting", "camera_frame_url": None, "camera_stream_url": None}
            return {
                "camera_state": "ready",
                "camera_frame_url": f"http://127.0.0.1:{self.port}/api/frame.jpeg?src={STREAM_NAME}",
                "camera_stream_url": f"rtsp://127.0.0.1:{self.rtsp_port}/{LIVE_NAME}",
            }
