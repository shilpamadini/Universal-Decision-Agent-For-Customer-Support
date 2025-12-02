
from __future__ import annotations

from typing import Any, Dict
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable


def build_intake_agent(model_name: str = "gpt-4o-mini") -> Runnable:
    """
    Intake Agent

    Input:
        - ticket_content
        - channel
        - tags
        - owner_name

    Output JSON:
        {
            "summary": "...",
            "normalized_issue": "...",
            "sentiment": "neutral|frustrated|angry|positive",
            "suspected_language": "en"
        }
    """

    model = ChatOpenAI(model=model_name)

    system = (
        "You are the Intake Agent for UDA-Hub. "
        "Your job is to read an incoming support ticket and normalize it.\n\n"
        "You MUST return a JSON object with:\n"
        "  - summary: 1–2 sentence summary\n"
        "  - normalized_issue: cleaned-up restatement\n"
        "  - sentiment: one of 'neutral', 'frustrated', 'angry', 'positive'\n"
        "  - suspected_language: ISO code (e.g., 'en')\n\n"
        "Return ONLY valid JSON."
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system),
            (
                "human",
                "Ticket content: {ticket_content}\n"
                "Channel: {channel}\n"
                "Tags: {tags}\n"
                "Owner name: {owner_name}\n\n"
                "Return ONLY the JSON object."
            ),
        ]
    )

    chain: Runnable = prompt | model.with_structured_output(method="json_mode")
    return chain
