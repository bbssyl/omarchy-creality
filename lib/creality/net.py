import socket

PROBE_TIMEOUT = 0.7


def port_open(host, port):
    try:
        with socket.create_connection((host, port), PROBE_TIMEOUT):
            return True
    except OSError:
        return False
