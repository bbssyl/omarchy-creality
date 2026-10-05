import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

NAN = "--nan" in sys.argv
STATE = {"state": "printing", "progress": 0.4}


def objects():
    return {"result": {"status": {
        "print_stats": {"state": STATE["state"], "filename": "cube.gcode", "print_duration": 400.0, "message": ""},
        "virtual_sdcard": {"progress": STATE["progress"]},
        "extruder": {"temperature": float("nan") if NAN else 205.3, "target": 210.0},
        "heater_bed": {"temperature": 59.8, "target": 60.0},
    }}}


class Handler(BaseHTTPRequestHandler):
    def reply(self, body):
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path
        routes = {
            "/printer/info": {"result": {"hostname": "voron-mock", "state": "ready"}},
            "/server/webcams/list": {"result": {"webcams": [{"snapshot_url": "/webcam/?action=snapshot"}]}},
            "/printer/objects/query": objects(),
        }
        self.reply(routes.get(path, {"result": {}}))

    def do_POST(self):
        action = urlparse(self.path).path.rsplit("/", 1)[-1]
        STATE["state"] = {"pause": "paused", "resume": "printing", "cancel": "cancelled"}.get(action, STATE["state"])
        sys.stdout.write(f"POST {self.path}\n")
        sys.stdout.flush()
        self.reply({"result": "ok"})

    def log_message(self, *args):
        return


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7125)
    parser.add_argument("--nan", action="store_true")
    HTTPServer(("127.0.0.1", parser.parse_args().port), Handler).serve_forever()
