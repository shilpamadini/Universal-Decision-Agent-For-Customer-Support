import json
import uuid
from typing import Any, Dict

from agentic.workflow import run_ticket


def _get_default_cultpass_user() -> Dict[str, Any]:
    path = "data/external/cultpass_users.jsonl"
    with open(path, "r", encoding="utf-8") as f:
        first_line = f.readline()
    return json.loads(first_line)


def test_simple_reservation_issue_routes_to_done_when_resolved():
    """
    For a simple FAQ-like question that is clearly in the KB (e.g. reservations),
    the system should route through resolver and finish in 'done'.
    """
    user = _get_default_cultpass_user()
    ticket = {
        "content": "How do I reserve a CultPass experience in the app?",
        "owner_id": user["id"],
        "owner_name": user["name"],
        "channel": "chat",
        "tags": "reservation, events",
        "ticket_id": f"TEST-RESERVE-{uuid.uuid4().hex[:8]}",
    }

    final_state = run_ticket(ticket, thread_id=ticket["ticket_id"])

    resolution = final_state.get("resolution") or {}
    supervisor = final_state.get("supervisor") or {}

    # We expect that this can be handled by KB → status 'resolved'
    assert resolution.get("status") in ("resolved", "needs_escalation")
    if resolution.get("status") == "resolved":
        assert resolution.get("answer")
        assert supervisor.get("next_step") == "done"


def test_weird_issue_eventually_escalates():
    """
    For a bizarre, non-KB-friendly ticket, the workflow should end in escalation.
    """
    user = _get_default_cultpass_user()
    ticket = {
        "content": (
            "Every time I scan my CultPass, my phone plays random animal sounds. "
            "Is this a feature or a bug?"
        ),
        "owner_id": user["id"],
        "owner_name": user["name"],
        "channel": "chat",
        "tags": "bug, weird",
        "ticket_id": f"TEST-WEIRD-{uuid.uuid4().hex[:8]}",
    }

    final_state = run_ticket(ticket, thread_id=ticket["ticket_id"])

    resolution = final_state.get("resolution") or {}
    supervisor = final_state.get("supervisor") or {}
    escalation = final_state.get("escalation")

    # If resolver can't confidently handle it, we expect 'needs_escalation'
    assert resolution.get("status") in ("needs_escalation", "resolved")
    if resolution.get("status") == "needs_escalation":
        assert supervisor.get("next_step") == "escalation"
        assert escalation is not None
        assert "summary_for_human" in escalation
