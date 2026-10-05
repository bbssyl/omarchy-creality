import base64
import hashlib
import os
import socket
import struct
import time

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
OP_CONT, OP_TEXT, OP_BIN, OP_CLOSE, OP_PING, OP_PONG = 0, 1, 2, 8, 9, 10


class WebSocketError(Exception):
    pass


MAX_PAYLOAD = 4 * 1024 * 1024
MID_FRAME_TIMEOUT = 5.0


def read_exact(sock, count, deadline=None):
    buffer = bytearray()
    while len(buffer) < count:
        if deadline is not None and time.monotonic() > deadline:
            raise WebSocketError("frame too slow")
        try:
            chunk = sock.recv(count - len(buffer))
        except socket.timeout:
            if deadline is not None or buffer:
                raise WebSocketError("timeout mid-frame")
            raise
        if not chunk:
            raise WebSocketError("connection closed")
        buffer.extend(chunk)
    return bytes(buffer)


def read_http_headers(sock):
    raw = bytearray()
    while b"\r\n\r\n" not in raw:
        chunk = sock.recv(1)
        if not chunk:
            raise WebSocketError("handshake closed")
        raw.extend(chunk)
        if len(raw) > 16384:
            raise WebSocketError("handshake too large")
    return raw.decode("latin-1")


def mask_payload(payload, key):
    return bytes(byte ^ key[index % 4] for index, byte in enumerate(payload))


def encode_frame(opcode, payload):
    length = len(payload)
    header = bytes([0x80 | opcode])
    if length < 126:
        header += bytes([0x80 | length])
    elif length < 65536:
        header += bytes([0x80 | 126]) + struct.pack(">H", length)
    else:
        header += bytes([0x80 | 127]) + struct.pack(">Q", length)
    key = os.urandom(4)
    return header + key + mask_payload(payload, key)


def read_frame(sock):
    first = read_exact(sock, 1)[0]
    previous_timeout = sock.gettimeout()
    sock.settimeout(MID_FRAME_TIMEOUT)
    try:
        return read_frame_body(sock, first, time.monotonic() + MID_FRAME_TIMEOUT)
    finally:
        sock.settimeout(previous_timeout)


def read_frame_body(sock, first, deadline):
    second = read_exact(sock, 1, deadline)[0]
    length = second & 0x7F
    if length == 126:
        length = struct.unpack(">H", read_exact(sock, 2, deadline))[0]
    elif length == 127:
        length = struct.unpack(">Q", read_exact(sock, 8, deadline))[0]
    if length > MAX_PAYLOAD:
        raise WebSocketError("frame too large")
    key = read_exact(sock, 4, deadline) if second & 0x80 else None
    payload = read_exact(sock, length, deadline)
    if key:
        payload = mask_payload(payload, key)
    return bool(first & 0x80), first & 0x0F, payload


class WebSocketClient:
    def __init__(self, host, port, timeout=5.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock = None
        self.fragments = bytearray()
        self.fragment_opcode = OP_TEXT

    def connect(self):
        self.sock = socket.create_connection((self.host, self.port), self.timeout)
        self.sock.settimeout(self.timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        request = (
            f"GET / HTTP/1.1\r\nHost: {self.host}:{self.port}\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n"
            "Sec-WebSocket-Protocol: wsslicer\r\n\r\n"
        )
        self.sock.sendall(request.encode())
        self.verify_handshake(read_http_headers(self.sock), key)

    def verify_handshake(self, response, key):
        lines = response.split("\r\n")
        if " 101 " not in lines[0]:
            raise WebSocketError(f"bad handshake: {lines[0]}")
        headers = {}
        for line in lines[1:]:
            if ":" in line:
                name, value = line.split(":", 1)
                headers[name.strip().lower()] = value.strip()
        expected = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
        if headers.get("sec-websocket-accept") != expected:
            raise WebSocketError("bad accept key")

    def send_text(self, text):
        self.sock.sendall(encode_frame(OP_TEXT, text.encode()))

    def receive(self, deadline=None):
        while True:
            if deadline is not None and time.monotonic() > deadline:
                raise socket.timeout("receive deadline")
            final, opcode, payload = read_frame(self.sock)
            message = self.handle_frame(final, opcode, payload)
            if message is not None:
                return message

    def handle_frame(self, final, opcode, payload):
        if opcode == OP_PING:
            self.sock.sendall(encode_frame(OP_PONG, payload))
            return None
        if opcode == OP_PONG:
            return None
        if opcode == OP_CLOSE:
            raise WebSocketError("closed by peer")
        return self.assemble(final, opcode, payload)

    def assemble(self, final, opcode, payload):
        if opcode != OP_CONT:
            self.fragments = bytearray()
            self.fragment_opcode = opcode
        self.fragments.extend(payload)
        if len(self.fragments) > MAX_PAYLOAD:
            raise WebSocketError("message too large")
        if not final:
            return None
        data = bytes(self.fragments)
        self.fragments = bytearray()
        return data.decode("utf-8", "replace") if self.fragment_opcode == OP_TEXT else data

    def close(self):
        if self.sock:
            try:
                self.sock.sendall(encode_frame(OP_CLOSE, b""))
            except OSError:
                pass
            self.sock.close()
            self.sock = None
