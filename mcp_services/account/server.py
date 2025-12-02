from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional

from fastmcp import FastMCP  
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Make project root importable (so `data.models` works)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data.models.cultpass import User as CultpassUser, Experience, Reservation
from data.models.udahub import User as CoreUser, Ticket

# MCP app setup

mcp = FastMCP(name="account")

# Database setup

PROJECT_ROOT = Path(__file__).resolve().parents[2]

CULTPASS_DB_PATH = os.getenv(
    "CULTPASS_DB_PATH",
    str(PROJECT_ROOT / "data" / "external" / "cultpass.db"),
)

UDAHUB_DB_PATH = os.getenv(
    "UDAHUB_DB_PATH",
    str(PROJECT_ROOT / "data" / "core" / "udahub.db"),
)

cultpass_engine = create_engine(f"sqlite:///{CULTPASS_DB_PATH}", echo=False, future=True)
udahub_engine = create_engine(f"sqlite:///{UDAHUB_DB_PATH}", echo=False, future=True)

CultpassSessionLocal = sessionmaker(bind=cultpass_engine)
UdahubSessionLocal = sessionmaker(bind=udahub_engine)


def get_cultpass_session():
    return CultpassSessionLocal()


def get_udahub_session():
    return UdahubSessionLocal()


# Helper serializers

def _cultpass_user_to_dict(user: CultpassUser) -> Dict[str, Any]:
    """Convert a CultPass user row to a plain dict."""
    return {
        "user_id": user.user_id,
        "name": getattr(user, "name", None),
        "email": getattr(user, "email", None),
    }


def _core_user_to_dict(user: CoreUser) -> Dict[str, Any]:
    """Convert a core UDA-Hub user row to a plain dict."""
    return {
        "user_id": user.user_id,
        "account_id": user.account_id,
        "external_user_id": user.external_user_id,
        "user_name": user.user_name,
    }


def _reservation_to_dict(res: Reservation, experience: Optional[Experience]) -> Dict[str, Any]:
    """Convert reservation + experience into a simple dict for agents."""
    exp_title = None
    exp_location = None
    if experience is not None:
        # These field names may vary; use getattr defensively
        exp_title = getattr(experience, "title", None) or getattr(experience, "name", None)
        exp_location = getattr(experience, "location", None)

    return {
        "reservation_id": res.reservation_id,
        "user_id": res.user_id,
        "experience_id": res.experience_id,
        "status": res.status,
        "experience_title": exp_title,
        "experience_location": exp_location,
    }


# MCP Tools

@mcp.tool
def account_get_user(external_user_id: str) -> Dict[str, Any]:
    """
    Look up a user by external CultPass user id, and return a combined view
    from the external CultPass DB and the core UDA-Hub DB.

    Args:
        external_user_id: The CultPass user id (from cultpass_users.jsonl).

    Returns:
        A dict with:
          - external_user: data from CultPass DB (or null)
          - core_user: data from UDA-Hub DB (or null)
          - reservation_count: number of reservations in CultPass DB
          - ticket_count: number of tickets in UDA-Hub DB
    """
    # External CultPass info
    with get_cultpass_session() as cp_session:
        cp_user = (
            cp_session.query(CultpassUser)
            .filter(CultpassUser.user_id == external_user_id)
            .first()
        )

        reservations_count = 0
        if cp_user:
            reservations_count = (
                cp_session.query(Reservation)
                .filter(Reservation.user_id == cp_user.user_id)
                .count()
            )

    # Core UDA-Hub info
    with get_udahub_session() as ud_session:
        core_user = (
            ud_session.query(CoreUser)
            .filter(
                CoreUser.external_user_id == external_user_id
            )
            .first()
        )

        ticket_count = 0
        if core_user:
            ticket_count = (
                ud_session.query(Ticket)
                .filter(Ticket.user_id == core_user.user_id)
                .count()
            )

    return {
        "external_user": _cultpass_user_to_dict(cp_user) if cp_user else None,
        "core_user": _core_user_to_dict(core_user) if core_user else None,
        "reservation_count": reservations_count,
        "ticket_count": ticket_count,
    }


@mcp.tool
def account_get_user_reservations(external_user_id: str) -> List[Dict[str, Any]]:
    """
    List all CultPass reservations for a given external user id,
    including basic experience information.

    Args:
        external_user_id: The CultPass user id.

    Returns:
        A list of reservations with:
          - reservation_id
          - user_id
          - experience_id
          - status
          - experience_title
          - experience_location (if available)
    """
    with get_cultpass_session() as cp_session:
        cp_user = (
            cp_session.query(CultpassUser)
            .filter(CultpassUser.user_id == external_user_id)
            .first()
        )

        if not cp_user:
            return []

        # Fetch reservations
        reservations = (
            cp_session.query(Reservation)
            .filter(Reservation.user_id == cp_user.user_id)
            .all()
        )

        # Fetch all experiences referenced by those reservations
        experience_ids = {res.experience_id for res in reservations}
        experiences_by_id = {}
        if experience_ids:
            experiences = (
                cp_session.query(Experience)
                .filter(Experience.experience_id.in_(list(experience_ids)))
                .all()
            )
            experiences_by_id = {exp.experience_id: exp for exp in experiences}

        return [
            _reservation_to_dict(res, experiences_by_id.get(res.experience_id))
            for res in reservations
        ]


# Entrypoint

if __name__ == "__main__":
    # Run with:  fastmcp run mcp_services/account/server.py
    mcp.run()
