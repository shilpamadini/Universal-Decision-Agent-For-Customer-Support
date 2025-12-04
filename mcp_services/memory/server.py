from __future__ import annotations

import os
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from fastmcp import FastMCP  
from sqlalchemy import (
    create_engine,
    Column,
    String,
    Text,
    DateTime,
)
from sqlalchemy.orm import declarative_base, sessionmaker

# MCP app setup

mcp = FastMCP(name="memory")

# Database setup (separate lightweight DB just for memory)

Base = declarative_base()

PROJECT_ROOT = Path(__file__).resolve().parents[2]

MEMORY_DB_PATH = os.getenv(
    "UDAHUB_MEMORY_DB_PATH",
    str(PROJECT_ROOT / "data" / "core" / "memory.db"),
)

engine = create_engine(f"sqlite:///{MEMORY_DB_PATH}", echo=False, future=True)
SessionLocal = sessionmaker(bind=engine)


def get_session():
    return SessionLocal()


class MemoryEntry(Base):
    __tablename__ = "memory_entries"

    id = Column(String, primary_key=True)
    external_user_id = Column(String, index=True, nullable=False)
    ticket_id = Column(String, nullable=True)
    content = Column(Text, nullable=False)
    meta = Column("metadata", Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


Base.metadata.create_all(bind=engine)


def _entry_to_dict(entry):
    return {
        "memory_id": entry.id,
        "external_user_id": entry.external_user_id,
        "ticket_id": entry.ticket_id,
        "content": entry.content,
        "metadata": json.loads(entry.meta) if entry.meta else {},
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
    }


# MCP Tools

@mcp.tool
def memory_write(
    external_user_id: str,
    content: str,
    ticket_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Write a long-term memory entry for a given external user id.

    Args:
        external_user_id: The external CultPass user id.
        content: Natural language summary of the memory (e.g., resolution, preference).
        ticket_id: Optional ticket id this memory is associated with.
        metadata: Optional structured metadata to store (will be JSON-encoded).

    Returns:
        A dict representing the saved memory entry.
    """
    mem_id = str(uuid.uuid4())
    metadata_json = json.dumps(metadata) if metadata is not None else None

    with get_session() as session:
        entry = MemoryEntry(
            id=mem_id,
            external_user_id=external_user_id,
            ticket_id=ticket_id,
            content=content,
            meta=metadata_json,
        )
        session.add(entry)       
        session.commit()         
        session.refresh(entry)   
        
    return _entry_to_dict(entry)


@mcp.tool
def memory_search(
    external_user_id: str,
    query: str,
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """
    Search long-term memory entries for a user using simple keyword matching.

    Args:
        external_user_id: The external CultPass user id.
        query: Text query describing what to look for (e.g., \"login issues\", \"refund\").
        limit: Maximum number of results.

    Returns:
        A list of matching memory entries, most recent first.
    """
    q = query.strip()
    if not q:
        return []

    with get_session() as session:
        # Simple LIKE search on content text (can be upgraded to semantic search later)
        like = f"%{q}%"
        entries = (
            session.query(MemoryEntry)
            .filter(
                MemoryEntry.external_user_id == external_user_id,
                MemoryEntry.content.ilike(like),
            )
            .order_by(MemoryEntry.created_at.desc())
            .limit(limit)
            .all()
        )

    return [_entry_to_dict(e) for e in entries]


@mcp.tool
def memory_get_all(
    external_user_id: str,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    Get all recent memories for a user (no query filtering).

    Args:
        external_user_id: The external CultPass user id.
        limit: Max number of entries to return.

    Returns:
        A list of memory entries ordered by recency (most recent first).
    """
    with get_session() as session:
        entries = (
            session.query(MemoryEntry)
            .filter(MemoryEntry.external_user_id == external_user_id)
            .order_by(MemoryEntry.created_at.desc())
            .limit(limit)
            .all()
        )

    return [_entry_to_dict(e) for e in entries]


# Entrypoint

if __name__ == "__main__":
    # Run with:  fastmcp run mcp_services/memory/server.py
    mcp.run()
