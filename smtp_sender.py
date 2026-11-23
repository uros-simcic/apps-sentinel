from copy import deepcopy
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import formatdate
import re
import smtplib
import ssl

from mailer import _address

MAX_MAIL_BYTES = 128 * 1024


def send_gmail(message, sender, recipient, password):
    _address(sender)
    _address(recipient)
    if (
        not isinstance(password, str)
        or not 1 <= len(password) <= 256
        or not isinstance(message, EmailMessage)
    ):
        raise ValueError("Invalid mail credentials or message")
    if (
        str(message["From"]) != sender
        or str(message["To"]) != recipient
        or message["Cc"] is not None
        or message["Bcc"] is not None
        or not re.fullmatch(
            r"<[0-9a-f]{64}@apps-sentinel\.invalid>",
            str(message["Message-ID"]),
        )
    ):
        raise ValueError("Message does not match intended delivery")

    outgoing = deepcopy(message)
    if outgoing["Date"] is None:
        outgoing["Date"] = formatdate(localtime=False, usegmt=True)
    if len(outgoing.as_bytes(policy=SMTP)) > MAX_MAIL_BYTES:
        raise ValueError("Email exceeds delivery size limit")

    try:
        with smtplib.SMTP_SSL(
            "smtp.gmail.com", 465,
            timeout=15, context=ssl.create_default_context(),
        ) as connection:
            connection.login(sender, password)
            refused = connection.send_message(
                outgoing, from_addr=sender, to_addrs=[recipient]
            )
            if refused:
                raise ValueError("Recipient was not accepted")
    except (OSError, ValueError):
        raise ValueError(
            "SMTP delivery was not confirmed"
        ) from None
