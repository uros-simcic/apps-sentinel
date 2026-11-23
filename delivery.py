from config import validate
from mailer import prepare_proposal_email
from state import load_state, save_state, upgrade_outbox


def deliver_proposal(
    api, config, state_issue, number, revision, sender, recipient, send
):
    """Caller must serialize all state writers.

    send(message) must return None only after transport acceptance.
    This function never retries a started delivery automatically.
    """
    validate(config)
    if config["mode"] != "active" or not callable(send):
        raise ValueError("Delivery requires active mode and a transport")

    state = upgrade_outbox(load_state(api, config, state_issue))
    entry = next(
        (
            row for row in state["outbox"]
            if row["proposal_issue"] == number
            and row["revision"] == revision
        ),
        None,
    )
    if entry is not None and (
        entry["status"] != "pending" or entry["attempts"] != 0
    ):
        return entry["status"]

    message = prepare_proposal_email(
        api, config, state_issue, number, revision, sender, recipient
    )
    if entry is None:
        entry = {
            "proposal_issue": number,
            "revision": revision,
            "status": "pending",
            "attempts": 0,
        }
        state["outbox"].append(entry)
        save_state(api, config, state_issue, state)

    entry["status"] = "sending"
    entry["attempts"] = 1
    save_state(api, config, state_issue, state)

    try:
        if send(message) is not None:
            raise ValueError("Transport did not confirm acceptance")
    except Exception:
        entry["status"] = "uncertain"
        save_state(api, config, state_issue, state)
        raise ValueError(
            "Email delivery is uncertain; automatic retry stopped"
        ) from None

    entry["status"] = "sent"
    save_state(api, config, state_issue, state)
    return "sent"
