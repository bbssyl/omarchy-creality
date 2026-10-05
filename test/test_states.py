import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

from creality.creality_ws import derive_state, normalize

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "k1max-job-start.log")
JOB = {"printFileName": "/usr/data/printer_data/gcodes/part.gcode"}


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


if __name__ == "__main__":
    unittest.main()
