from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from delivery import deliver_proposal


class DeliveryTests(unittest.TestCase):
    def run_delivery(self, send, existing=None, save_error=False):
        config = json.loads(Path("config.example.json").read_text())
        config["mode"] = "active"
        state = {
            "schema_version": 3,
            "checks": [],
            "executions": [],
            "outbox": [] if existing is None else [existing],
        }
        saves = []

        def save(api, config, number, value, *, expected):
            if save_error:
                raise ValueError("State was not confirmed")
            self.assertEqual(expected, saves[-1] if saves else state)
            saves.append(deepcopy(value))

        with (
            patch("delivery.load_state", return_value=state),
            patch("delivery.save_state", side_effect=save),
            patch("delivery.prepare_proposal_email", return_value="message"),
        ):
            result = deliver_proposal(
                Mock(), config, 7, 8, "b" * 64,
                "sender@example.com", "owner@example.com", send,
            )
        return result, saves

    def test_records_sending_before_transport_and_sent_afterward(self):
        observed = []

        def send(message):
            self.assertEqual(message, "message")
            observed.append("accepted")

        result, saves = self.run_delivery(send)
        self.assertEqual(result, "sent")
        self.assertEqual(observed, ["accepted"])
        self.assertEqual(
            [state["outbox"][0]["status"] for state in saves],
            ["pending", "sending", "sent"],
        )
        self.assertEqual(saves[-1]["outbox"][0]["attempts"], 1)

    def test_unconfirmed_state_prevents_transport(self):
        send = Mock()
        with self.assertRaises(ValueError):
            self.run_delivery(send, save_error=True)
        send.assert_not_called()

    def test_started_deliveries_are_not_resent(self):
        for status in ("sending", "sent", "uncertain"):
            send = Mock()
            entry = {
                "proposal_issue": 8,
                "revision": "b" * 64,
                "status": status,
                "attempts": 1,
            }
            result, saves = self.run_delivery(send, existing=entry)
            self.assertEqual(result, status)
            self.assertEqual(saves, [])
            send.assert_not_called()

    def test_transport_failure_stops_without_exposing_error_details(self):
        send = Mock(side_effect=RuntimeError("private transport detail"))
        with self.assertRaisesRegex(
            ValueError, "^Email delivery is uncertain; automatic retry stopped$"
        ):
            self.run_delivery(send)
        send.assert_called_once_with("message")
