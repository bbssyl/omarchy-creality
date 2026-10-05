import ipaddress
import json
import os
import tempfile

DEFAULTS = {"finished_lit_minutes": 10, "notify": True}
INTEGER_KEYS = ("finished_lit_minutes", "ws_port", "http_port", "camera_port")
BOOLEAN_KEYS = ("notify",)
TEXT_KEYS = ("model", "hostname", "light_macro", "light_object")
PROTOCOLS = ("creality-ws", "moonraker")
ALLOWED_KEYS = INTEGER_KEYS + BOOLEAN_KEYS + TEXT_KEYS + ("ip", "protocol")
MAX_TEXT_LENGTH = 120


def config_path():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.environ.get("CREALITY_CONFIG") or os.path.join(base, "omarchy-creality", "config.json")


def cache_dir():
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return os.environ.get("CREALITY_CACHE") or os.path.join(base, "omarchy-creality")


def load(path=None):
    try:
        with open(path or config_path(), encoding="utf-8") as handle:
            stored = json.load(handle)
    except (OSError, ValueError):
        stored = {}
    return {**DEFAULTS, **(stored if isinstance(stored, dict) else {})}


def save(config, path=None):
    target = path or config_path()
    os.makedirs(os.path.dirname(target), exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=os.path.dirname(target))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(config, handle, indent=2, ensure_ascii=False)
        os.replace(temporary, target)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise


def coerce(key, value):
    if key not in ALLOWED_KEYS:
        raise ValueError(f"unknown key: {key}")
    if key in INTEGER_KEYS:
        number = int(value)
        if not 0 <= number <= 65535:
            raise ValueError(f"out of range: {key}")
        return number
    if key in BOOLEAN_KEYS:
        return str(value).lower() in ("1", "true", "yes", "on")
    return validate_text(key, value)


def validate_text(key, value):
    if key == "ip":
        return str(ipaddress.ip_address(value))
    if key == "protocol" and value not in PROTOCOLS:
        raise ValueError(f"unknown protocol: {value}")
    if len(value) > MAX_TEXT_LENGTH or any(ord(char) < 32 for char in value):
        raise ValueError(f"invalid value for {key}")
    return value


def update(pairs, path=None):
    config = load(path)
    changes = {}
    for pair in pairs:
        key, separator, value = pair.partition("=")
        if not separator:
            raise ValueError(f"expected key=value: {pair}")
        changes[key] = coerce(key, value)
    config.update(changes)
    save(config, path)
    return config


def update_address(address, path=None):
    config = load(path)
    config["ip"] = address
    save(config, path)


def is_configured(config):
    return bool(config.get("ip") and config.get("protocol"))
