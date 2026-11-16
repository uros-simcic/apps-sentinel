from approval import check_approval
from state import load_state, save_state, upgrade_state


def claim_execution(api, config, state_issue, number, revision):
    approved = check_approval(
        api, config, state_issue, number, revision
    )
    state = upgrade_state(load_state(api, config, state_issue))
    comment_id = approved["comment_id"]
    if any(
        row["comment_id"] == comment_id
        for row in state["executions"]
    ):
        raise ValueError("Approval has already been consumed")

    state["executions"].append({
        "proposal_issue": number,
        "revision": approved["proposal"]["revision"],
        "comment_id": comment_id,
        "status": "claimed",
    })
    save_state(api, config, state_issue, state)
    return approved
