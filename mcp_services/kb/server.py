from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Optional, Dict, Any

from fastmcp import FastMCP  # fastmcp>=2.10.6
from sqlalchemy import create_engine, or_
from sqlalchemy.orm import sessionmaker

# Ensure project root is on sys.path so `data.models` can be imported

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data.models.udahub import Knowledge  

# MCP app setup

mcp = FastMCP(name="kb")

# Database setup

UDAHUB_DB_PATH = os.getenv(
    "UDAHUB_DB_PATH",
    str(PROJECT_ROOT / "data" / "core" / "udahub.db"),
)

engine = create_engine(f"sqlite:///{UDAHUB_DB_PATH}", echo=False, future=True)
SessionLocal = sessionmaker(bind=engine)


def get_session():
    return SessionLocal()


def _article_to_dict(article: Knowledge, score: Optional[float] = None) -> Dict[str, Any]:
    """Convert Knowledge row to a plain dict for MCP responses."""
    data = {
        "article_id": article.article_id,
        "account_id": article.account_id,
        "title": article.title,
        "content": article.content,
        "tags": article.tags,
    }
    if score is not None:
        data["score"] = score
    return data


# Tools

@mcp.tool
def kb_get(article_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a single knowledge base article by its article_id.

    Returns:
        A dict with article fields, or null if not found.
    """
    with get_session() as session:
        article = (
            session.query(Knowledge)
            .filter(Knowledge.article_id == article_id)
            .first()
        )
        if not article:
            return None
        return _article_to_dict(article)


@mcp.tool
def kb_search(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Search knowledge base articles by simple keyword matching.

    Args:
        query: Natural language query describing the user's issue.
        limit: Maximum number of articles to return.

    Returns:
        A list of article dicts with a simple relevance score.
    """
    q = query.strip()
    if not q:
        return []

    with get_session() as session:
        like = f"%{q}%"
        results = (
            session.query(Knowledge)
            .filter(
                or_(
                    Knowledge.title.ilike(like),
                    Knowledge.content.ilike(like),
                    Knowledge.tags.ilike(like),
                )
            )
            .all()
        )

        query_words = [w.lower() for w in q.split() if w.strip()]

        scored: List[Dict[str, Any]] = []
        for art in results:
            text = f"{art.title}\n{art.content}\n{art.tags or ''}".lower()
            hits = sum(1 for w in query_words if w in text)
            scored.append(_article_to_dict(art, score=float(hits)))

        scored.sort(key=lambda a: (-a.get("score", 0.0), a["title"]))

        return scored[:limit]


# Entrypoint

if __name__ == "__main__":
    # Run with:  fastmcp run mcp_services/kb/server.py
    mcp.run()
