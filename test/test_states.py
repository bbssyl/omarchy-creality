import json
import os
import re
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

from creality.creality_ws import KNOWN_STATUS_KEYS, CrealityWsAdapter, derive_state, normalize, thumbnail_url
from creality.moonraker import MAX_RESPONSE_BYTES, http_json

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "k1max-job-start.log")
JOB = {"printFileName": "/usr/data/printer_data/gcodes/part.gcode"}


def build_adapter():
    return CrealityWsAdapter({"ip": "192.0.2.1"})


def replay_fixture():
    merged, observed = {}, []
    with open(FIXTURE, encoding="utf-8") as handle:
        lines = handle.readlines()
    for line in lines:
        match = re.match(r"^\S+\s+(\{.*\})\s*$", line)
        if not match:
            continue
        merged.update(json.loads(match.group(1)))
        status = normalize(dict(merged), "192.0.2.1")
        if not observed or observed[-1][0] != status["state"]:
            observed.append((status["state"], status["prep_step"]))
    return observed


class CapturedJobStart(unittest.TestCase):
    def test_should_follow_stop_then_calibration_then_printing_when_replaying_capture(self):
        states = [state for state, _ in replay_fixture()]

        self.assertEqual(states, ["paused", "stopping", "idle", "starting", "preparing", "printing"])

    def test_should_report_calibration_steps_only_while_preparing(self):
        steps = [step for state, step in replay_fixture() if state == "preparing"]

        self.assertEqual(steps, [0])


class DeriveState(unittest.TestCase):
    def test_should_be_printing_when_self_test_finished(self):
        raw = {**JOB, "state": 1, "enableSelfTest": 1, "withSelfTest": 100, "printProgress": 3}

        self.assertEqual(derive_state(raw), "printing")

    def test_should_be_preparing_when_self_test_running(self):
        raw = {**JOB, "state": 1, "enableSelfTest": 1, "withSelfTest": 3}

        self.assertEqual(derive_state(raw), "preparing")

    def test_should_be_printing_when_self_test_disabled(self):
        raw = {**JOB, "state": 1, "enableSelfTest": 0, "withSelfTest": 0}

        self.assertEqual(derive_state(raw), "printing")

    def test_should_be_idle_when_stopped_during_calibration(self):
        raw = {**JOB, "state": 4, "enableSelfTest": 1, "withSelfTest": 3}

        self.assertEqual(derive_state(raw), "idle")

    def test_should_prefer_error_over_other_states(self):
        raw = {**JOB, "state": 9, "err": {"errcode": 5}}

        self.assertEqual(derive_state(raw), "error")

    def test_should_be_paused_when_state_five_even_during_self_test(self):
        raw = {**JOB, "state": 5, "enableSelfTest": 1, "withSelfTest": 2}

        self.assertEqual(derive_state(raw), "paused")

    def test_should_be_starting_and_stopping_for_transition_states(self):
        self.assertEqual(derive_state({"state": 9}), "starting")
        self.assertEqual(derive_state({"state": 7}), "stopping")


class ThumbnailUrl(unittest.TestCase):
    def test_should_strip_gcode_extension_and_keep_path_segment(self):
        raw = {"printFileName": "/usr/data/printer_data/gcodes/part.gcode"}

        self.assertEqual(thumbnail_url(raw, "192.0.2.1"), "http://192.0.2.1/downloads/humbnail/part.png")

    def test_should_be_none_when_no_file_is_loaded(self):
        self.assertIsNone(thumbnail_url({}, "192.0.2.1"))

    def test_should_url_encode_special_characters_in_filename(self):
        raw = {"printFileName": "my model #2.gcode"}

        self.assertEqual(thumbnail_url(raw, "192.0.2.1"), "http://192.0.2.1/downloads/humbnail/my%20model%20%232.png")


class HandleMessageAllowlist(unittest.TestCase):
    def test_should_ignore_unknown_keys_and_report_no_change(self):
        adapter = build_adapter()

        changed = adapter.handle_message(None, json.dumps({"bogusKey": "x", "anotherJunk": 1}))

        self.assertFalse(changed)
        self.assertEqual(adapter.raw, {})

    def test_should_retain_only_known_keys_from_mixed_payload(self):
        adapter = build_adapter()

        changed = adapter.handle_message(
            None, json.dumps({"nozzleTemp": 42, "bogusKey": "x", "state": 1})
        )

        self.assertTrue(changed)
        self.assertEqual(adapter.raw, {"nozzleTemp": 42, "state": 1})

    def test_should_bound_retained_state_under_sustained_unknown_key_flood(self):
        adapter = build_adapter()

        for index in range(50):
            adapter.handle_message(None, json.dumps({f"junkKey{index}": index}))

        self.assertLessEqual(len(adapter.raw), len(KNOWN_STATUS_KEYS))
        self.assertEqual(adapter.raw, {})

    def test_should_still_populate_status_from_known_fields(self):
        adapter = build_adapter()

        changed = adapter.handle_message(
            None,
            json.dumps(
                {
                    **JOB,
                    "state": 1,
                    "printProgress": 50,
                    "nozzleTemp": 210,
                    "targetNozzleTemp": 215,
                }
            ),
        )

        self.assertTrue(changed)
        status = adapter.status()
        self.assertEqual(status["state"], "printing")
        self.assertEqual(status["progress"], 50)
        self.assertEqual(status["nozzle"], {"cur": 210, "target": 215})


def build_static_body_handler(body):
    class StaticBodyHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if body:
                self.wfile.write(body)

        def log_message(self, *args):
            return

    return StaticBodyHandler


def start_static_body_server(body):
    server = HTTPServer(("127.0.0.1", 0), build_static_body_handler(body))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def stop_static_body_server(server):
    server.shutdown()
    server.server_close()


def static_body_server_url(server):
    return f"http://127.0.0.1:{server.server_address[1]}/"


class HttpJsonResponseCap(unittest.TestCase):
    def test_should_decode_response_at_or_under_cap(self):
        server = start_static_body_server(json.dumps({"ok": True}).encode())

        try:
            result = http_json(static_body_server_url(server))
        finally:
            stop_static_body_server(server)

        self.assertEqual(result, {"ok": True})

    def test_should_raise_when_response_exceeds_cap(self):
        server = start_static_body_server(b"0" * (MAX_RESPONSE_BYTES + 1024))

        try:
            with self.assertRaises(ValueError):
                http_json(static_body_server_url(server))
        finally:
            stop_static_body_server(server)

    def test_should_return_empty_dict_for_empty_body(self):
        server = start_static_body_server(b"")

        try:
            result = http_json(static_body_server_url(server))
        finally:
            stop_static_body_server(server)

        self.assertEqual(result, {})


if __name__ == "__main__":
    unittest.main()
