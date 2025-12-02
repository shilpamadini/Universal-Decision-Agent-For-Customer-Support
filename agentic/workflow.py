from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict
import asyncio
from dotenv import load_dotenv
load_dotenv()

from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import RunnableConfig

from agentic.agents.intake_agent import build_intake_agent
from agentic.agents.classifier_agent import build_classifier_agent
from agentic.agents.escalation_agent import build_escalation_agent
from agentic.agents.supervisor_agent import build_supervisor_agent

from agentic.tools.knowledge_client import get_kb_search_tool
from agentic.tools.account_client import (
    get_account_get_user_tool,
    get_account_get_user_reservations_tool,
)
from agentic.tools.memory_client import (
    get_memory_write_tool,
    get_memory_search_tool,
)


# State schema

class TicketState(TypedDict, total=False):
    """
    Shared state for the UDA-Hub workflow.

    Keys:
        ticket:        Raw ticket info (content + metadata)
        intake:        Output of IntakeAgent
        classification:Output of ClassifierAgent
        resolution:    Output of Resolver node (agent)
        escalation:    Output of EscalationAgent
        supervisor:    Output of SupervisorAgent
    """

    ticket: Dict[str, Any]
    intake: Dict[str, Any]
    classification: Dict[str, Any]
    resolution: Dict[str, Any]
    escalation: Dict[str, Any]
    supervisor: Dict[str, Any]


# Global models & tools

# Core LLM (used by resolver + helper prompts)
LLM = ChatOpenAI(model="gpt-4o-mini")

# Instantiate agents 
INTAKE_AGENT = build_intake_agent()
CLASSIFIER_AGENT = build_classifier_agent()
ESCALATION_AGENT = build_escalation_agent()
SUPERVISOR_AGENT = build_supervisor_agent()

# MCP-backed tools (LangChain tools)
KB_SEARCH_TOOL = get_kb_search_tool()
ACCOUNT_GET_USER_TOOL = get_account_get_user_tool()
ACCOUNT_GET_RESERVATIONS_TOOL = get_account_get_user_reservations_tool()
MEMORY_WRITE_TOOL = get_memory_write_tool()
MEMORY_SEARCH_TOOL = get_memory_search_tool()


# Node implementations


def intake_node(state: TicketState) -> TicketState:
    """
    Normalize the ticket and extract a summary, sentiment, etc.
    """
    ticket = state["ticket"]

    result = INTAKE_AGENT.invoke(
        {
            "ticket_content": ticket.get("content", ""),
            "channel": ticket.get("channel", "unknown"),
            "tags": ticket.get("tags", ""),
            "owner_name": ticket.get("owner_name", ""),
        }
    )

    return {"intake": result}


def classifier_node(state: TicketState) -> TicketState:
    """
    Classify issue type, urgency, complexity, and whether it likely needs
    escalation.
    """
    ticket = state["ticket"]
    intake = state["intake"]

    result = CLASSIFIER_AGENT.invoke(
        {
            "ticket_content": ticket.get("content", ""),
            "normalized_issue": intake.get("normalized_issue", ""),
            "sentiment": intake.get("sentiment", "neutral"),
            "channel": ticket.get("channel", "unknown"),
            "tags": ticket.get("tags", ""),
        }
    )

    return {"classification": result}



async def resolver_node(state: TicketState, config: RunnableConfig) -> TicketState:
    """
    Resolver node (agent):

    - Uses MCP-backed tools:
        * KB_SEARCH_TOOL: search relevant KB articles
        * ACCOUNT_GET_USER_TOOL / ACCOUNT_GET_RESERVATIONS_TOOL: personalization
        * MEMORY_SEARCH_TOOL: recall prior interactions
        * MEMORY_WRITE_TOOL: store successful resolutions
    - Uses LLM to craft final answer grounded in KB + tools.
    - Sets a confidence score and decides resolved vs needs_escalation.
    """

    ticket = state["ticket"]
    intake = state.get("intake", {})
    classification = state.get("classification", {})

    user_issue = intake.get("normalized_issue") or ticket.get("content", "")
    external_user_id = ticket.get("owner_id")
    ticket_id = ticket.get("ticket_id")

    # Knowledge retrieval via KB tool (async)
    
    used_kb_articles = []
    kb_results = []
    top_score = 0.0

    if KB_SEARCH_TOOL is not None and user_issue:
        kb_results = await KB_SEARCH_TOOL.ainvoke(
            {"query": user_issue, "limit": 5}
        ) or []
        if kb_results:
            used_kb_articles = [
                a.get("article_id") for a in kb_results if a.get("article_id")
            ]
            top_score = float(kb_results[0].get("score", 0.0) or 0.0)

    if not kb_results:
        confidence = 0.2
    else:
        # map score roughly into [0.3, 0.95]
        confidence = max(0.3, min(0.95, top_score / 2.0 + 0.3))

    # Account lookup for personalization (async)
    
    account_snippet = ""

    if external_user_id and ACCOUNT_GET_USER_TOOL is not None:
        user_info = await ACCOUNT_GET_USER_TOOL.ainvoke(
            {"external_user_id": external_user_id}
        )
        if user_info:
            account_snippet += f"User profile: {user_info}\n\n"

    if external_user_id and ACCOUNT_GET_RESERVATIONS_TOOL is not None:
        reservations = await ACCOUNT_GET_RESERVATIONS_TOOL.ainvoke(
            {"external_user_id": external_user_id}
        )
        if reservations:
            account_snippet += f"Current reservations: {reservations}\n\n"

    # Long-term memory search (async)
    memory_snippet = ""
    if external_user_id and MEMORY_SEARCH_TOOL is not None:
        memories = await MEMORY_SEARCH_TOOL.ainvoke(
            {
                "external_user_id": external_user_id,
                "query": user_issue,
                "limit": 5,
            }
        )
        if memories:
            memory_snippet = f"Relevant prior memories: {memories}\n\n"

    # Prepare KB context for the LLM
    kb_snippet = ""
    if kb_results:
        kb_snippet_lines = []
        for art in kb_results[:3]:
            kb_snippet_lines.append(
                f"Title: {art.get('title')}\nContent:\n{art.get('content')}\n"
            )
        kb_snippet = "\n\n---\n\n".join(kb_snippet_lines)

    # Decide if we should attempt resolution or escalate
    likely_resolvable = bool(kb_results) and confidence >= 0.5

    if not likely_resolvable:
        resolution = {
            "status": "needs_escalation",
            "answer": (
                "I'm not fully confident I can resolve this automatically based on the "
                "available knowledge. A human support agent should review this ticket."
            ),
            "confidence": confidence,
            "used_kb_articles": used_kb_articles,
            "notes_for_human": (
                "KB search returned no strong matches or low scores. "
                "Please manually review the issue and consider updating the KB."
            ),
        }
        return {"resolution": resolution}

    # Use LLM to craft a grounded answer (sync LLM call is OK here)
    system_prompt = (
        "You are the Resolver Agent for UDA-Hub, helping CultPass users.\n"
        "You MUST base your answer ONLY on the knowledge base articles and data provided.\n"
        "If something is not covered in the knowledge, do not invent a policy.\n\n"
        "Respond in a friendly, concise tone.\n"
    )

    user_prompt = (
        f"User issue (normalized): {user_issue}\n\n"
        f"Issue type: {classification.get('issue_type', 'other')}\n"
        f"Urgency: {classification.get('urgency', 'low')}\n"
        f"Complexity: {classification.get('complexity', 'low')}\n\n"
        f"{account_snippet}"
        f"{memory_snippet}"
        "Relevant knowledge base articles:\n"
        f"{kb_snippet}\n\n"
        "Using ONLY the information above, draft a final answer to the user.\n"
        "Do NOT mention internal tools or KB article IDs. "
        "Just explain what the user should do or what we can do for them."
    )

    llm_resp = LLM.invoke(
        [
            ("system", system_prompt),
            ("human", user_prompt),
        ]
    )
    answer_text = llm_resp.content if hasattr(llm_resp, "content") else str(llm_resp)

    status = "resolved"
    notes_for_human = (
        "Resolved automatically using KB content. "
        "If the user replies that this didn't help, escalate."
    )

    resolution = {
        "status": status,
        "answer": answer_text,
        "confidence": confidence,
        "used_kb_articles": used_kb_articles,
        "notes_for_human": notes_for_human,
    }

    # Write long-term memory (async, best-effort)
    if external_user_id and MEMORY_WRITE_TOOL is not None:
        try:
            await MEMORY_WRITE_TOOL.ainvoke(
                {
                    "external_user_id": external_user_id,
                    "ticket_id": ticket_id,
                    "content": f"Resolved issue: {user_issue}\nAnswer: {answer_text}",
                    "metadata": {
                        "issue_type": classification.get("issue_type"),
                        "kb_articles": used_kb_articles,
                        "confidence": confidence,
                    },
                }
            )
        except Exception:
            # Don't fail the whole workflow if memory write fails.
            pass

    return {"resolution": resolution}

def escalation_node(state: TicketState) -> TicketState:
    """
    Prepare a structured escalation summary for a human agent.
    """
    ticket = state["ticket"]
    intake = state.get("intake", {})
    classification = state.get("classification", {})
    resolution = state.get("resolution", {})

    resolver_notes = resolution.get("notes_for_human") if resolution else None

    result = ESCALATION_AGENT.invoke(
        {
            "ticket_content": ticket.get("content", ""),
            "intake_summary": intake.get("summary", ""),
            "sentiment": intake.get("sentiment", "neutral"),
            "classification": classification,
            "resolver_notes": resolver_notes or "",
        }
    )

    return {"escalation": result}


def supervisor_node(state: TicketState) -> TicketState:
    """
    Decide the next step: 'resolver', 'escalation', or 'done'.
    """
    intake = state.get("intake", {})
    classification = state.get("classification", {})
    resolution = state.get("resolution", {})

    result = SUPERVISOR_AGENT.invoke(
        {
            "summary": intake.get("summary", ""),
            "issue_type": classification.get("issue_type", "other"),
            "urgency": classification.get("urgency", "low"),
            "complexity": classification.get("complexity", "low"),
            "resolver_status": resolution.get("status") if resolution else None,
            "resolver_confidence": resolution.get("confidence") if resolution else None,
        }
    )

    return {"supervisor": result}


# Routing logic for conditional edges

def route_from_supervisor(state: TicketState) -> str:
    """
    Inspect supervisor.next_step and decide which node to visit next.
    """
    supervisor = state.get("supervisor", {}) or {}
    next_step = supervisor.get("next_step", "done")

    if next_step == "resolver":
        return "resolver"
    if next_step == "escalation":
        return "escalation"
    # default
    return END


# Build and compile the LangGraph workflow

def build_workflow():
    """
    Build and compile the UDA-Hub multi-agent workflow graph.

    Nodes:
        - intake
        - classifier
        - supervisor
        - resolver
        - escalation

    Edges:
        START -> intake -> classifier -> supervisor
        supervisor -> resolver / escalation / END (conditional)
        resolver -> supervisor
        escalation -> END
    """
    graph = StateGraph(TicketState)

    # Add nodes
    graph.add_node("intake", intake_node)
    graph.add_node("classifier", classifier_node)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("resolver", resolver_node)
    graph.add_node("escalation", escalation_node)

    # Fixed edges
    graph.add_edge(START, "intake")
    graph.add_edge("intake", "classifier")
    graph.add_edge("classifier", "supervisor")
    graph.add_edge("resolver", "supervisor")
    graph.add_edge("escalation", END)

    # Conditional edges from supervisor
    graph.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {
            "resolver": "resolver",
            "escalation": "escalation",
            END: END,
        },
    )

    # Use MemorySaver for short-term conversation memory
    memory = MemorySaver()
    app = graph.compile(checkpointer=memory)
    return app


# Convenience: instantiate a module-level workflow app
orchestrator = build_workflow()


def run_ticket(ticket: Dict[str, Any], thread_id: str) -> TicketState:
    """
    Convenience wrapper to run the LangGraph workflow for a single ticket.

    This uses the async API under the hood (ainvoke) because some nodes,
    such as the resolver, are async-only (they call async MCP tools).
    """

    initial_state: TicketState = {
        "ticket": ticket,
        "intake": None,
        "classification": None,
        "resolution": None,
        "escalation": None,
        "supervisor": None,
    }

    config = {
        "configurable": {
            "thread_id": thread_id,
        }
    }

    return asyncio.run(orchestrator.ainvoke(initial_state, config=config))

