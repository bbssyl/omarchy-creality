import argparse
import json
import os
import sys
import threading
import time
import urllib.parse
import urllib.request

from . import config as config_store
from .creality_ws import CrealityWsAdapter
from .demo import DemoAdapter
from .discovery import discover
from .lifecycle import install_parent_guard
from .model import offline_status, public_view
from .moonraker import MoonrakerAdapter
from .watch import Watcher, emit_unconfigured

ADAPTERS = {"creality-ws": CrealityWsAdapter, "moonraker": MoonrakerAdapter}


def build_adapter(config):
    if os.environ.get("CREALITY_DEMO") == "1" or config.get("demo"):
        return DemoAdapter(config)
    adapter_class = ADAPTERS.get(config.get("protocol"))
    if adapter_class is None:
        raise SystemExit(f"unknown protocol: {config.get('protocol')}")
    return adapter_class(config)


def parse_arguments(argv):
    parser = argparse.ArgumentParser(prog="creality-bridge")
    parser.add_argument("--config", default=None)
    parser.add_argument("--host")
    parser.add_argument("--protocol", choices=sorted(ADAPTERS))
    parser.add_argument("--ws-port", type=int)
    parser.add_argument("--http-port", type=int)
    sub = parser.add_subparsers(dest="command", required=True)
    watch = sub.add_parser("watch")
    watch.add_argument("--demo", action="store_true")
    sub.add_parser("status")
    found = sub.add_parser("discover")
    found.add_argument("--subnet", action="append")
    control = sub.add_parser("cmd")
    control.add_argument("action", choices=["pause", "resume", "stop", "light"])
    control.add_argument("argument", nargs="?")
    snapshot = sub.add_parser("snapshot")
    snapshot.add_argument("url")
    snapshot.add_argument("out")
    setter = sub.add_parser("set-config")
    setter.add_argument("pairs", nargs="+")
    return parser.parse_args(argv)


def effective_config(args):
    config = config_store.load(args.config)
    overrides = {"ip": args.host, "protocol": args.protocol, "ws_port": args.ws_port, "http_port": args.http_port}
    config.update({key: value for key, value in overrides.items() if value is not None})
    if getattr(args, "demo", False):
        config["demo"] = True
    return config


def run_watch(args, config):
    install_parent_guard()
    demo = config.get("demo") or os.environ.get("CREALITY_DEMO") == "1"
    if not demo and not config_store.is_configured(config):
        emit_unconfigured()
        threading.Event().wait()
    config.setdefault("protocol", "demo")
    config.setdefault("ip", "demo")
    try:
        Watcher(config, build_adapter, args.config).run()
    except KeyboardInterrupt:
        return 0


def run_status(config):
    try:
        status = build_adapter(config).fetch_once()
    except Exception:
        status = offline_status(config)
    print(json.dumps(public_view(status)))


SNAPSHOT_MAX_BYTES = 5 * 1024 * 1024
SNAPSHOT_DEADLINE_SECONDS = 10.0


def download_snapshot(url):
    if urllib.parse.urlparse(url).scheme not in ("http", "https"):
        raise ValueError("snapshot url must be http or https")
    deadline = time.monotonic() + SNAPSHOT_DEADLINE_SECONDS
    chunks, total = [], 0
    with urllib.request.urlopen(url, timeout=8) as response:
        if not response.headers.get_content_type().startswith("image/"):
            raise ValueError("snapshot is not an image")
        while True:
            chunk = response.read(65536)
            if not chunk:
                return b"".join(chunks)
            total += len(chunk)
            if total > SNAPSHOT_MAX_BYTES or time.monotonic() > deadline:
                raise ValueError("snapshot too large or too slow")
            chunks.append(chunk)


def run_snapshot(url, out):
    data = download_snapshot(url)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    temporary = out + ".part"
    try:
        with open(temporary, "wb") as handle:
            handle.write(data)
        os.replace(temporary, out)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def run_command(config, args):
    try:
        build_adapter(config).command(args.action, args.argument)
    except Exception as error:
        print(json.dumps({"ok": False, "error": str(error)}))
        return 1
    print(json.dumps({"ok": True}))
    return 0


def run_snapshot_command(args):
    try:
        run_snapshot(args.url, args.out)
    except Exception as error:
        sys.stderr.write(f"snapshot failed: {error}\n")
        return 1
    return 0


def run_set_config(args):
    try:
        config_store.update(args.pairs, args.config)
    except (ValueError, OSError) as error:
        print(json.dumps({"ok": False, "error": str(error)}))
        return 1
    print(json.dumps({"ok": True}))
    return 0


def main(argv=None):
    args = parse_arguments(sys.argv[1:] if argv is None else argv)
    if args.command == "set-config":
        return run_set_config(args)
    config = effective_config(args)
    if args.command == "watch":
        return run_watch(args, config)
    if args.command == "status":
        run_status(config)
    elif args.command == "discover":
        ports = (config.get("ws_port") or 9999, config.get("http_port") or 7125)
        print(json.dumps(discover(args.subnet, *ports)))
    elif args.command == "cmd":
        return run_command(config, args)
    elif args.command == "snapshot":
        return run_snapshot_command(args)
    return 0
