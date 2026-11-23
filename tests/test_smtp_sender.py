from email.message import EmailMessage
import ssl
import unittest
from unittest.mock import patch

from smtp_sender import send_gmail


class SMTPTests(unittest.TestCase):
    def message(self):
        message = EmailMessage()
        message["From"] = "sender@example.com"
        message["To"] = "owner@example.com"
        message["Subject"] = "Example proposal"
        message["Message-ID"] = (
            "<" + "a" * 64 + "@apps-sentinel.invalid>"
        )
        message.set_content("Complete example patch\n")
        return message

    def send(self, message):
        return send_gmail(
            message, "sender@example.com",
            "owner@example.com", "example-test-password",
        )

    def test_uses_verified_tls_and_explicit_recipient(self):
        message = self.message()
        with patch("smtp_sender.smtplib.SMTP_SSL") as client:
            connection = client.return_value.__enter__.return_value
            connection.send_message.return_value = {}
            self.assertIsNone(self.send(message))

        args, kwargs = client.call_args
        self.assertEqual(args, ("smtp.gmail.com", 465))
        self.assertEqual(kwargs["timeout"], 15)
        self.assertTrue(kwargs["context"].check_hostname)
        self.assertEqual(
            kwargs["context"].verify_mode, ssl.CERT_REQUIRED
        )
        connection.login.assert_called_once_with(
            "sender@example.com", "example-test-password"
        )
        outgoing = connection.send_message.call_args.args[0]
        self.assertEqual(outgoing.get_content(), message.get_content())
        self.assertIsNotNone(outgoing["Date"])
        self.assertIsNone(message["Date"])
        self.assertEqual(
            connection.send_message.call_args.kwargs,
            {
                "from_addr": "sender@example.com",
                "to_addrs": ["owner@example.com"],
            },
        )

    def test_hidden_or_changed_recipient_stops_before_connection(self):
        for change in ("hidden", "changed"):
            message = self.message()
            if change == "hidden":
                message["Bcc"] = "other@example.com"
            else:
                message.replace_header("To", "other@example.com")
            with patch("smtp_sender.smtplib.SMTP_SSL") as client:
                with self.assertRaises(ValueError):
                    self.send(message)
            client.assert_not_called()

    def test_oversized_email_stops_before_connection(self):
        message = self.message()
        message.set_content("x" * 131073)
        with patch("smtp_sender.smtplib.SMTP_SSL") as client:
            with self.assertRaises(ValueError):
                self.send(message)
        client.assert_not_called()

    def test_connection_error_is_sanitized_without_retry(self):
        with patch(
            "smtp_sender.smtplib.SMTP_SSL",
            side_effect=OSError("private server detail"),
        ) as client:
            with self.assertRaisesRegex(
                ValueError, "^SMTP delivery was not confirmed$"
            ):
                self.send(self.message())
        client.assert_called_once()

    def test_recipient_refusal_is_not_reported_as_success(self):
        with patch("smtp_sender.smtplib.SMTP_SSL") as client:
            connection = client.return_value.__enter__.return_value
            connection.send_message.return_value = {
                "owner@example.com": (550, b"Refused")
            }
            with self.assertRaises(ValueError):
                self.send(self.message())
        connection.send_message.assert_called_once()
