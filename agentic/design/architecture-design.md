# 1.Overview

UDA-Hub is an end-to-end automated customer-support workflow powered by:

* LangGraph for multi-agent orchestration

* LLM-driven agents for intake, classification, resolution, escalation, and supervision

* MCP (Model Context Protocol) servers acting as external tools:

    * kb → knowledge-base search

    * account → user profile & reservations

    * memory → ticket memory & history

The system processes a customer ticket from raw text → resolution or escalation, while storing contextual memory for future personalization.

## 2.Architecture Diagram 


![Graph](https://github.com/shilpamadini/Universal-Decision-Agent-For-Customer-Support/blob/8765e484244cbeb24af5deb5dff2d88e7cbcf8fd/agentic/design/Graph.jpeg)



## 3.System Components
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

## 4. Agents
### 4.1 Intake Agent

Goal: Normalize raw ticket text.

Outputs:

* summary

* normalized_issue

* sentiment

Used for downstream classification & reasoning.

### 4.2 Classifier Agent

Goal: Predict:

* issue_type

* urgency (low/medium/high)

* complexity

* escalation

Classifier shapes routing decisions.

### 4.3 Supervisor Agent

Goal: Decide next action:

* resolver

* escalation

* END

Based on:

* classifier outputs

* resolver confidence

* agent tool results (KB, memory, account info)

Acts as the “traffic controller” of the workflow.

### 4.4 Resolver Agent

Uses Tools:

* kb_search

* account_get_user

* account_get_user_reservations

* memory_search

Goal: Attempt automated resolution:

* pull KB articles

* fetch user profile & account context

* retrieve previous memories

* build a candidate answer

Returns:

* answer

* used_kb_articles

* confidence

* status (solved / not_solved / needs_escalation)

### 4.5 Escalation Agent

Creates a human-friendly escalation summary:

* clear problem statement

* context from intake & classification

* resolver notes

* recommended next steps

* target department

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

## 6. Data Flow

```
sequenceDiagram
    participant User
    participant Intake
    participant Classifier
    participant Supervisor
    participant Resolver
    participant KB
    participant Account
    participant Memory
    participant Escalation

    User->>Intake: Raw ticket message
    Intake->>Classifier: summary + normalized issue
    Classifier->>Supervisor: classification result

    alt Supervisor -> Resolver
        Supervisor->>Resolver: resolve ticket
        Resolver->>KB: search knowledge base
        Resolver->>Account: get user profile + reservations
        Resolver->>Memory: search prior memories
        Resolver->>Supervisor: resolution attempt
    end

    alt Escalation required
        Supervisor->>Escalation: escalate
        Escalation->>Memory: write summary
    end
```

## 7. State Definition

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

## 8. Technologies Used

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

## 9. Deployment & Execution
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

## 11. Conclusion

The UDA-Hub architecture provides a robust, scalable, and testable design for automated ticket resolution using:

* Multi-agent LLM reasoning

* External tool integrations

* Persistent memory

* Deterministic workflow routing

* Modular MCP services

It is fully extensible for real-world customer-support automation or enterprise ticketing systems.