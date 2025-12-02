import json
import uuid
from typing import Any, Dict

from agentic.workflow import run_ticket


def _get_default_cultpass_user() -> Dict[str, Any]:
    """
    Helper: load the first CultPass user.
    """
    path = "data/external/cultpass_users.jsonl"
    with open(path, "r", encoding="utf-8") as f:
        first_line = f.readline()
    return json.loads(first_line)


def test_login_issue_flow():
    """
    End-to-end test for a login problem.

    Even if the system escalates due to low KB confidence, this demonstrates:
    - intake
    - classification
    - resolver attempt
    - supervisor decision
    - escalation handoff structure
    """
    user = _get_default_cultpass_user()

    ticket = {
        "content": "Hi, I can't log in to my CultPass account and I don't get the reset email.",
        "owner_id": user["id"],
        "owner_name": user["name"],
        "channel": "chat",
        "tags": "login, access",
        "ticket_id": f"TEST-LOGIN-{uuid.uuid4().hex[:8]}",
    }

    final_state = run_ticket(ticket, thread_id=ticket["ticket_id"])

    intake = final_state.get("intake") or {}
    classification = final_state.get("classification") or {}
    resolution = final_state.get("resolution") or {}
    supervisor = final_state.get("supervisor") or {}

    # Intake sanity
    assert "summary" in intake
    assert "normalized_issue" in intake

    # Classification sanity
    assert classification.get("issue_type") in ("login", "technical", "other")
    assert classification.get("urgency") in ("low", "medium", "high")

    # Resolver should at least produce a structured resolution object
    assert "status" in resolution
    assert "confidence" in resolution

    # Supervisor should choose a next_step consistent with resolution
    assert supervisor.get("next_step") in ("resolver", "escalation", "done")


def test_extreme_unknown_issue_end_to_end():
    """
    End-to-end test for a very strange issue where escalation is expected.
    """
    user = _get_default_cultpass_user()

    ticket = {
        "content": (
            "My CultPass card caused my screen to turn purple and show random numbers "
            "whenever I tap it. I think it's haunted."
        ),
        "owner_id": user["id"],
        "owner_name": user["name"],
        "channel": "chat",
        "tags": "bug, paranormal",
        "ticket_id": f"TEST-HAUNTED-{uuid.uuid4().hex[:8]}",
    }

    final_state = run_ticket(ticket, thread_id=ticket["ticket_id"])

    resolution = final_state.get("resolution") or {}
    supervisor = final_state.get("supervisor") or {}
    escalation = final_state.get("escalation") or final_state.get("escalation")

    assert "status" in resolution
    assert resolution.get("status") in ("needs_escalation", "resolved")

    if resolution.get("status") == "needs_escalation":
        assert supervisor.get("next_step") == "escalation"
        assert escalation is not None
        assert "summary_for_human" in escalation
