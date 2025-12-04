# 1. Overview

UDA-Hub is an end-to-end automated customer-support workflow powered by:

* LangGraph for multi-agent orchestration

* LLM-driven agents for intake, classification, resolution, escalation, and supervision

* MCP (Model Context Protocol) servers acting as external tools:

    * kb → knowledge-base search

    * account → user profile & reservations

    * memory → ticket memory & history

The system processes a customer ticket from raw text → resolution or escalation, while storing contextual memory for future personalization.

## 2. Architecture Diagram 


![Graph](https://github.com/shilpamadini/Universal-Decision-Agent-For-Customer-Support/blob/8765e484244cbeb24af5deb5dff2d88e7cbcf8fd/agentic/design/Graph.jpeg)



## 3. System Components
### 3.1 LangGraph Orchestrator

The orchestrator defines:

* State schema (TypedDict)

* Nodes (agents)

* Edges (routing logic)

* Conditional transitions for:

* resolve → supervisor → end

* escalate → end

* partial resolution → resolver loop

Located in:
agentic/workflow.py

### 3.2 Logging & Observability

UDA-Hub implements structured JSON logging end-to-end so every ticket can be fully traced through Intake → Classification → Supervisor → Resolver → Escalation → Completion.

All logs are emitted using a shared JSON logger (logger.get_logger()), used by:

* agentic/workflow.py — node lifecycle, tool calls, supervisor decisions, resolver scoring

* 03_agentic_app.py — CLI + demo workflow events

### Log destinations

- **Stdout** – convenient during local development / debugging  
- **File** – JSONL file with one event per line:

```
logs/uda_hub.jsonl

```

each line is a a JSON object, for example:
```
{
  "timestamp": "2025-12-02T09:42:10.123456Z",
  "level": "INFO",
  "message": "supervisor_decision",
  "extra": {
    "ticket_id": "DEMO-TICKET-001",
    "thread_id": "DEMO-TICKET-001",
    "issue_type": "login",
    "urgency": "high",
    "complexity": "medium",
    "next_step": "escalation",
    "resolver_status": "needs_escalation",
    "resolver_confidence": 0.2
  }
}


```

the system logs:

* Node Lifecycle Events

Each workflow node logs both start and end events:

    * node_start_intake, node_end_intake

    * node_start_classifier, node_end_classifier

    * node_start_supervisor, node_end_supervisor

    * node_start_resolver, node_end_resolver

    * node_start_escalation, node_end_escalation

Fields include:

    * ticket_id

    * thread_id

* Supervisor Decisions

Event: supervisor_decision

Fields captured:

    * ticket_id, thread_id

    * issue_type, urgency, complexity

    * resolver_status (nullable)

    * resolver_confidence

    * next_step → resolver | escalation | done

    * reason
    
* Tool Calls (MCP Tools)

All MCP tools emit start and end logs:

    * tool_call_kb_search_start / tool_call_kb_search_end

    * tool_call_account_get_user_start / tool_call_account_get_user_end

    * tool_call_account_get_reservations_start / tool_call_account_get_reservations_end

    * tool_call_memory_search_start / tool_call_memory_search_end

Fields captured:

    * ticket_id, thread_id

    * tool_name

    * Sanitized inputs (e.g., query, external_user_id)

    * Result metrics, e.g.:

        * result_count

        * memories_count

        * reservations_count

        * KB scoring:

        * top_score

        * lexical_overlap

        * salient_overlap

        * salient_tokens

        * salient_hits

* Resolver Outcomes

The resolver logs detailed decision information:

    * resolver_kb_confidence

    * resolver_decision_resolved

    * resolver_decision_needs_escalation

Fields include:

    * kb_result_count

    * top_score

    * lexical_overlap

    * salient_overlap

    * confidence

    * Decision status
    
* Final Workflow Summary

Event: workflow_completed

Fields:

    * ticket_id, thread_id

    * final_status → resolved | needs_escalation

    * final_confidence
    
* CLI / Demo Events

For interactive or scripted runs:

    * cli_ticket_received

    * cli_workflow_result

    * demo_ticket_received

    * demo_workflow_result

Fields include:

    * issue_type, urgency, complexity

    * supervisor_next_step

    * resolution_status

    * resolution_confidence

These structured logs provide:

    * Full traceability of every ticket

    * Complete visibility into agent decisions

    * Debugging of KB search quality

    * Auditing of tool interactions

    * End-to-end observability for platform monitoring and analytics

This enables reliable analysis of system behavior and ensures tickets can be tracked from first user input → final resolution with no black boxes.

## 4. Agent Interaction & Decision Flow

UDA-Hub uses a **Supervisor-based multi-agent architecture**:

- A central **Supervisor Agent** is responsible for routing and high-level decisions.
- Specialized worker agents (**Intake, Classifier, Resolver, Escalation**) each focus on a narrow, well-defined task.
- All agents share a common state managed by **LangGraph**, and the Supervisor decides:
  - which agent to invoke next,
  - when to stop,
  - when to escalate to a human.

This pattern makes it easy to:
- Add new agents (e.g., a SentimentPrioritizer or RefundAgent),
- Evolve routing logic without changing individual agent implementations,
- Observe and debug decisions through structured state and logs.
### 4.1. Intake Agent
   - Receives the raw ticket payload (text + metadata).
   - Normalizes and enriches the ticket into:
     - `summary`
     - `normalized_issue`
     - `sentiment`
     - `suspected_language`
   - Writes these fields into the shared LangGraph state under `intake`.

### 4.2. Classifier Agent
   - Reads `ticket` and `intake` from state.
   - Produces:
     - `issue_type` (e.g., `login`, `billing`, `reservation`)
     - `urgency` (low / medium / high)
     - `complexity` (simple / medium / complex)
     - `should_escalate_immediately` (bool)
   - Writes results into `classification` in the state.

### 4.3. Supervisor Agent
   - Reads `ticket`, `intake`, `classification`, and the latest `resolution` (if any).
   - Applies decision logic to choose `next_step`, such as:
     - `"resolver"` (try to auto-resolve)
     - `"escalation"` (send to human)
     - `"end"` (ticket handled)
   - Writes the decision and rationale into `supervisor`.

### 4.4 Resolver Agent
   - Triggered when `supervisor.next_step == "resolver"`.
   - Uses MCP tools:
     - `kb_search` → retrieve relevant KB articles
     - `account_get_user` / `account_get_user_reservations` → account context
     - `memory_search` → similar past tickets / resolutions
   - Synthesizes a candidate answer and confidence score.
   - Updates `resolution` with:
     - `answer`
     - `status` (`solved`, `not_solved`, `needs_escalation`)
     - `confidence`
     - `used_kb_articles`
   - The Supervisor then reads `resolution` and decides whether to:
     - End the workflow, or
     - Loop back for another attempt, or
     - Escalate.

### 4.5. Escalation Agent
   - Triggered when `supervisor.next_step == "escalation"` or classification demands immediate escalation.
   - Reads `ticket`, `intake`, `classification`, and `resolution`.
   - Produces a structured summary for human handoff:
     - `summary_for_human`
     - `recommended_department`
     - `proposed_next_steps`
   - Writes escalation info into `escalation` and may write a memory via `memory_write`.

### 4.6 Input & Output Handling

UDA-Hub is designed to handle **normalized ticket objects** rather than raw strings. Each ticket input has the following shape:

```jsonc
{
  "ticket_id": "string",
  "content": "Hi, I can't log in to my account...",
  "owner_id": "external-user-id",
  "owner_name": "string",
  "channel": "chat | email | web | other",
  "tags": "comma-separated tags (optional)"
}

```

### 4.7 How Different Ticket Types Are Handled

* Login / Access Issues

    * Classifier sets issue_type = "login", typically with higher urgency.

    * Resolver prioritizes KB articles tagged login, password, access.

If the user reports no reset email and confidence is low, Supervisor tends to escalate to Technical Support.

* Billing / Subscription Questions

    * issue_type = "billing" or subscription.

    * Resolver uses KB search with billing tags and may use account tools to check the user profile.

    * If policies are clear and found in KB, auto-resolution is likely.

* Reservation / Experience Issues

    * issue_type = "reservation" or experience.

    * Resolver queries:

        * account_get_user_reservations for concrete reservation details.

        * KB articles on cancellations, no-shows, or event rules.

* General / Unknown Issues

    * issue_type = "other".

    * Resolver attempts a best-effort KB search using normalized_issue.

    * If low confidence or no matches, Supervisor routes to escalation.

### 5.3 Expected Outputs

For each processed ticket, the final LangGraph state includes:

* ticket → original request metadata.

* intake → normalized issue and sentiment analysis.

* classification → issue type, urgency, complexity.

* resolution:

    * status: "solved" | "not_solved" | "needs_escalation"

    * answer: human-readable suggested reply to the customer (if auto-resolved).

    * confidence: float (0–1) representing model confidence.

    * used_kb_articles: list of article IDs/titles.

* escalation (optional):

    * summary_for_human

    * recommended_department

    * proposed_next_steps

The **external observable** outputs are either:

    * An automated reply (resolution.answer), or

    * An escalation package for a human agent (escalation.*).


## 5. MCP Tools (External Services)
### 5.1 Knowledge Base Server (kb)

Located in: mcp_services/kb/server.py

* loads JSONL KB articles

* supports semantic search

* returns list of candidate articles with text

Tool names:

* kb_search

* kb_get

### 5.2 Account Server

Located in: mcp_services/account/server.py

Provides:

* User profile lookups

* Reservation history

Tool names:

* account_get_user

* account_get_user_reservations

### 5.3 Memory Server

Located in: mcp_services/memory/server.py

Stores ticket history including:

* ticket ID

* content

* metadata

* timestamp

Tool names:

* memory_write

* memory_search

* memory_get_all

## 6. State Definition

Each workflow step updates portions of the shared LangGraph state.

```
State Fields:

ticket: dict
intake: dict
classification: dict
resolution: dict
escalation: dict
supervisor: dict
```

All transitions occur through state reducers, ensuring deterministic workflow execution.

## 7. Technologies Used

Core System

* Python 3.11

* LangChain

* LangGraph (multi-agent workflows)

* MCP (Model Context Protocol)

* OpenAI models (gpt-4o-mini, etc.)

* Databases SQLite (Core + External DBs)

* JSONL documents for KB

* Testing - pytest  async test support

* Visualization - Mermaid diagrams
* LangGraph graph export

## 8. Deployment & Execution
* Run MCP servers
* python mcp_services/kb/server.py
* python mcp_services/account/server.py
* python mcp_services/memory/server.py

* Run the full agentic workflow
    ```
    python 03_agentic_app.py --mode demo

    ```
* Run tests
    ```
      pytest -q
    ```

## 9. Conclusion

The UDA-Hub architecture provides a robust, scalable, and testable design for automated ticket resolution using:

* Multi-agent LLM reasoning

* External tool integrations

* Persistent memory

* Deterministic workflow routing

* Modular MCP services

It is fully extensible for real-world customer-support automation or enterprise ticketing systems.
