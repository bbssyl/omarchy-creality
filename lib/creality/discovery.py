import ipaddress
import itertools
import json
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

from .creality_ws import DEFAULT_WS_PORT, REQUEST_STATUS
from .net import port_open
from .moonraker import DEFAULT_PORT as DEFAULT_HTTP_PORT, http_json
from .wsclient import WebSocketClient, WebSocketError

MAX_HOSTS = 1024


def local_subnets():
    try:
        output = subprocess.run(["ip", "-j", "-4", "addr"], capture_output=True, text=True, timeout=3).stdout
        interfaces = json.loads(output or "[]")
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
    subnets = []
    for interface in interfaces:
        if interface.get("ifname") == "lo":
            continue
        for address in interface.get("addr_info", []):
            prefix = max(int(address.get("prefixlen", 24)), 24)
            network = ipaddress.ip_network(f"{address['local']}/{prefix}", strict=False)
            if network not in subnets and network.is_private:
                subnets.append(network)
    return subnets


def hosts_in(subnets):
    hosts = itertools.chain.from_iterable(network.hosts() for network in subnets)
    return [str(host) for host in itertools.islice(hosts, MAX_HOSTS)]


def identify_creality(host, port):
    client = WebSocketClient(host, port, 2.0)
    try:
        client.connect()
        client.send_text(json.dumps(REQUEST_STATUS))
        deadline = time.monotonic() + 2.5
        while time.monotonic() < deadline:
            payload = json.loads(client.receive())
            if isinstance(payload, dict) and ("model" in payload or "hostname" in payload):
                return {"model": payload.get("model"), "hostname": payload.get("hostname")}
    except (OSError, WebSocketError, ValueError):
        return None
    finally:
        client.close()
    return None


def identify_moonraker(host, port):
    try:
        info = http_json(f"http://{host}:{port}/printer/info", 2.0).get("result", {})
    except (OSError, ValueError):
        return None
    return {"model": None, "hostname": info.get("hostname")}


def probe_host(host, ws_port, http_port):
    found = []
    if port_open(host, ws_port):
        identity = identify_creality(host, ws_port)
        if identity:
            found.append({"ip": host, "protocol": "creality-ws", **identity})
    if port_open(host, http_port):
        identity = identify_moonraker(host, http_port)
        if identity:
            found.append({"ip": host, "protocol": "moonraker", **identity})
    return found


def prefer_one_per_address(printers):
    chosen = {}
    for printer in printers:
        current = chosen.get(printer["ip"])
        if current is None or printer["protocol"] == "creality-ws":
            chosen[printer["ip"]] = printer
    return list(chosen.values())


def discover(subnets=None, ws_port=DEFAULT_WS_PORT, http_port=DEFAULT_HTTP_PORT):
    networks = [ipaddress.ip_network(item, strict=False) for item in subnets] if subnets else local_subnets()
    hosts = hosts_in(networks)
    if not hosts:
        hosts = [str(network.network_address) for network in networks if network.num_addresses == 1]
    with ThreadPoolExecutor(max_workers=256) as pool:
        results = pool.map(lambda host: probe_host(host, ws_port, http_port), hosts)
    return prefer_one_per_address([printer for group in results for printer in group])


def match_by_hostname(printers, hostname):
    return next((printer for printer in printers if hostname and printer.get("hostname") == hostname), None)
