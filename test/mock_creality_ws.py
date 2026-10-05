import argparse
import base64
import hashlib
import json
import struct
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingTCPServer, BaseRequestHandler

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
JPEG = bytes.fromhex("ffd8ffe000104a46494600010100000100010000ffd9")
STATE = {"withSelfTest": 100, "state": 1, "printProgress": 10, "pause": 0, "lightSw": 1, "stopped": False}
SETTINGS = {"finish_after": 6.0, "fail_after": 0.0, "nan": False, "stall": False, "replay": False}
STARTED = time.monotonic()


def full_status():
    elapsed = int(time.monotonic() - STARTED)
    nozzle = float("nan") if SETTINGS["nan"] else "219.5"
    return {
        "model": "K1C", "hostname": "K1C-MOCK", "modelVersion": "F021",
        "nozzleTemp": nozzle, "targetNozzleTemp": 220, "bedTemp0": "60.0", "targetBedTemp0": 60,
        "boxTemp": 35, "enableSelfTest": 1, "withSelfTest": STATE["withSelfTest"], "printProgress": STATE["printProgress"], "printJobTime": elapsed,
        "printLeftTime": 0 if STATE["withSelfTest"] < 100 else max(0, 600 - elapsed), "printFileName": "/mnt/UDISK/printer_data/gcodes/benchy.gcode",
        "state": STATE["state"], "lightSw": STATE["lightSw"], "err": {"errcode": 0, "key": 0},
    }


def frame(opcode, payload, fin=True):
    length = len(payload)
    head = bytes([(0x80 if fin else 0) | opcode])
    if length < 126:
        return head + bytes([length]) + payload
    if length < 65536:
        return head + bytes([126]) + struct.pack(">H", length) + payload
    return head + bytes([127]) + struct.pack(">Q", length) + payload


def read_exact(sock, count):
    data = b""
    while len(data) < count:
        chunk = sock.recv(count - len(data))
        if not chunk:
            raise ConnectionError
        data += chunk
    return data


def read_client_frame(sock):
    first, second = read_exact(sock, 2)
    length = second & 0x7F
    if length == 126:
        length = struct.unpack(">H", read_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack(">Q", read_exact(sock, 8))[0]
    key = read_exact(sock, 4)
    payload = bytes(b ^ key[i % 4] for i, b in enumerate(read_exact(sock, length)))
    return first & 0x0F, payload


def apply_set(params):
    if "pause" in params:
        STATE["state"] = 5 if params["pause"] else 1
    if params.get("stop"):
        STATE["state"] = 4
    if "lightSw" in params:
        STATE["lightSw"] = params["lightSw"]
    sys.stdout.write(f"SET {json.dumps(params)}\n")
    sys.stdout.flush()


REPLAY_STEPS = [(9, 100, 0), (1, 0, 0), (1, 2, 0), (1, 3, 0), (1, 4, 0), (1, 5, 0), (1, 100, 0),
                (1, 100, 3), (5, 100, 3), (7, 100, 3), (4, 100, 3)]


def replay():
    for state, step, progress in REPLAY_STEPS:
        STATE.update({"state": state, "withSelfTest": step, "printProgress": progress})
        time.sleep(2)


def advance():
    if SETTINGS["replay"]:
        replay()
        return
    while True:
        time.sleep(1)
        if STATE["state"] == 1:
            STATE["printProgress"] = min(100, STATE["printProgress"] + 15)
            elapsed = time.monotonic() - STARTED
            if SETTINGS["fail_after"] and elapsed > SETTINGS["fail_after"]:
                STATE["error"] = True
            if STATE["printProgress"] >= 100 and elapsed > SETTINGS["finish_after"]:
                STATE["state"] = 2


class Handler(BaseRequestHandler):
    def handle(self):
        try:
            self.handshake()
            threading.Thread(target=self.push, daemon=True).start()
            self.serve()
        except (ConnectionError, OSError):
            return

    def handshake(self):
        raw = b""
        while b"\r\n\r\n" not in raw:
            raw += self.request.recv(1)
        key = [l.split(": ")[1] for l in raw.decode().split("\r\n") if l.lower().startswith("sec-websocket-key")][0]
        accept = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
        self.request.sendall(
            ("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
             f"Sec-WebSocket-Accept: {accept}\r\n\r\n").encode())
        self.lock = threading.Lock()

    def send(self, data):
        with self.lock:
            self.request.sendall(data)

    def push(self):
        try:
            while True:
                time.sleep(1.5)
                self.send(frame(1, json.dumps({"ModeCode": "heart_beat"}).encode()))
                partial = {k: v for k, v in full_status().items() if k in ("printProgress", "state", "nozzleTemp", "printLeftTime", "withSelfTest", "enableSelfTest")}
                self.send(frame(1, json.dumps(partial).encode()))
        except (ConnectionError, OSError):
            return

    def send_fragmented(self, text):
        payload = text.encode()
        middle = len(payload) // 2
        self.send(frame(1, payload[:middle], fin=False) + frame(9, b"hi") + frame(0, payload[middle:]))

    def serve(self):
        while True:
            opcode, payload = read_client_frame(self.request)
            if opcode == 8:
                return
            if opcode == 1:
                self.on_text(payload.decode())

    def stall(self):
        self.send(bytes([0x81, 10]) + b"ab")
        time.sleep(30)

    def on_text(self, text):
        if text == "ok":
            sys.stdout.write("HEARTBEAT_ACK\n")
            sys.stdout.flush()
            return
        message = json.loads(text)
        if message.get("method") == "get" and SETTINGS["stall"]:
            self.stall()
        elif message.get("method") == "get":
            self.send_fragmented(json.dumps(full_status()))
        elif message.get("method") == "set":
            apply_set(message["params"])


class Camera(BaseHTTPRequestHandler):
    def do_GET(self):
        body, kind = JPEG, "image/jpeg"
        if "big" in self.path:
            body = b"x" * (6 * 1024 * 1024)
        if "text" in self.path:
            body, kind = b"<html>", "text/html"
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        return


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=9999)
    parser.add_argument("--camera-port", type=int, default=8080)
    parser.add_argument("--finish-after", type=float, default=6.0)
    parser.add_argument("--nan", action="store_true")
    parser.add_argument("--replay", action="store_true")
    parser.add_argument("--stall", action="store_true")
    arguments = parser.parse_args()
    SETTINGS["nan"] = arguments.nan
    SETTINGS["replay"] = arguments.replay
    SETTINGS["stall"] = arguments.stall
    SETTINGS["finish_after"] = arguments.finish_after
    ThreadingTCPServer.allow_reuse_address = True
    threading.Thread(target=advance, daemon=True).start()
    threading.Thread(target=HTTPServer(("127.0.0.1", arguments.camera_port), Camera).serve_forever, daemon=True).start()
    ThreadingTCPServer(("127.0.0.1", arguments.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
