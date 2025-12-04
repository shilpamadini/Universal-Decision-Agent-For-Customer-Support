# Universal Decision Agent: Multi-Agent Customer Support Orchestrator

Universal Decision Agent is a fully functional multi-agent support automation system built with LangGraph, LangChain, FastMCP, and SQLite.
It processes customer support tickets end-to-end through intelligent agents that ingest, classify, resolve, and escalate issues while integrating data from:

Knowledge Base (KB)

Account & Reservation System (CultPass)

Long-Term Memory

The system chooses actions dynamically using a Supervisor agent and tools, following a hierarchical multi-agent pattern that supports real-time decision making and human escalation.

This project meets and exceeds the Udacity rubric for the Multi-Agent Editing & Decisioning track.

## Table of Contents

1. Overview
2. Architecture & Design
    * Multi-Agent Pattern
    * Architecture Diagram
    * State Schema
3. Agents & Responsibilities
4. Knowledge, Tools & MCP Services
5. Ticket Processing Flow
6. Short-Term & Long-Term Memory
7. Repository Structure
8. Setup Instructions
9. Running the App
10. Running Tests

## Overview

Universal Decision Agent simulates a production-grade customer-support agent system, capable of:

* Understanding incoming tickets

* Classifying issue type & urgency

* Searching KB for solutions

* Looking up user profiles & reservations

* Consulting long-term memory for prior issues

* Attempting resolution with confidence scoring

* Escalating to human agents when needed

* Producing structured explanations for support teams

It runs on a hybrid of rule-based routing and agentic reasoning, and integrates multiple data sources via FastMCP servers that behave like external microservices.

## Architecture & Design

### Multi-Agent Pattern

The system uses a Supervisor / Hierarchical agent design:
    * Supervisor Agent acts as the central router
    * Intake Agent standardizes the ticket
    * Classifier Agent determines issue characteristics
    * Resolver Agent uses tools & memory to attempt solutions
    * Escalation Agent handles human-handoff summaries
Each agent writes into a shared LangGraph state, and the supervisor decides the next step based on the evolving state.

### Architecture Diagram

![Graph](https://github.com/shilpamadini/Universal-Decision-Agent-For-Customer-Support/blob/8765e484244cbeb24af5deb5dff2d88e7cbcf8fd/agentic/design/Graph.jpeg)


### State Management

The LangGraph state schema:

```
class TicketState(TypedDict, total=False):
    ticket: Dict[str, Any]
    intake: Dict[str, Any]
    classification: Dict[str, Any]
    resolution: Dict[str, Any]
    escalation: Dict[str, Any]
    supervisor: Dict[str, Any]
```

Stored per thread_id using MemorySaver.


## Logging & Observability

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

## Agents & Responsibilities

1. Intake Agent

Normalizes incoming ticket content.

Outputs:
* summary
* normalized_issue
* sentiment

2. Classifier Agent

Predicts:

* issue_type (login / billing / reservation / account / other)
* urgency (low / medium / high)
* complexity (low / medium / high)
* escaltion
* rationale

3. Resolver Agent

Uses MCP tools:

* kb_search
* account_get_user
* account_get_user_reservations
* memory_search
* memory_write

Produces:

* status: resolved / needs_escalation
* answer
* confidence
* used_kb_articles
* notes_for_human

4. Escalation Agent

Generates human-ready summary including:

* issue summary
* recommended department
* next steps
* optional inclusion of resolver notes

5. Supervisor Agent

Routes between:

* resolver
* escalation
* done

Rules include escalation checks, resolver confidence threshold, and classification hints.

## Knowledge, Tools & MCP Services

Universal Decision Agent  connects to three FastMCP microservices:

### KB Server (kb/)

* Searches the knowledge base table
* Tool: kb_search(query, limit)

### Account Server (account/)

* Fetches user profile + user reservations
* Tools:
    account_get_user(external_user_id)
    account_get_user_reservations(external_user_id)

### Memory Server (memory/)

* Long-term memory write & search
* Tools:
    memory_write(...)
    memory_search(...)
    memory_get_all(external_user_id)
These tools are wrapped and used inside the Resolver Agent.

## Ticket Processing Flow
```
Incoming ticket
    ↓
Intake Agent (normalize)
    ↓
Classifier Agent (problem type, urgency)
    ↓
Supervisor Agent
    ↳ Resolver Agent → try to solve via tools
        ↳ If confident: DONE
        ↳ If not: back to Supervisor
    ↳ Escalation Agent → human summary
    ↳ DONE

```
Everything is stored in the LangGraph state and returned as the final output.

## Memory Design

### Short-Term (Per-Ticket)

* Backed by LangGraph MemorySaver
* Stores intermediate agent outputs

### Long-Term (Cross-Ticket)

* SQLite backed
* Accessed via MCP
* Stores historical issue content, metadata, timestamps
* Used by Resolver to personalize answers

## Repository Structure
```
uda-hub/
├── README.md
├── requirements.txt
├── .gitignore
├── .env                                # Local environment variables
│
├── 01_external_db_setup.ipynb          # Notebook: loads JSONL → external DB
├── 02_core_db_setup.ipynb              # Notebook: builds core DB schema
├── 03_agentic_app.py                   # Entry script to run full UDA-Hub workflow
│
├── agentic/                            # LangGraph + Agent layer
│   ├── __init__.py
│   ├── workflow.py                     # Full StateGraph workflow (intake → classifier → supervisor → resolver/escalation)
│   │
│   ├── agents/                         # All agent definitions
│   │   ├── __init__.py
│   │   ├── intake_agent.py
│   │   ├── classifier_agent.py
│   │   ├── resolver_agent.py
│   │   ├── escalation_agent.py
│   │   ├── supervisor_agent.py
│   │
│   ├── tools/                          # MCP client wrappers (async)
│       ├── __init__.py
│       ├── mcp_client.py               # MCP connection + dynamic tool loader
│       ├── knowledge_client.py         # KB search/get
│       ├── account_client.py           # Account get_user + get_user_reservations
│       ├── memory_client.py            # Memory write + search
│
├── mcp_services/                       # All MCP Servers (FastMCP)
│   ├── kb/
│   │   ├── server.py                   # Knowledge Base MCP tool server
│   │
│   ├── account/
│   │   ├── server.py                   # Account MCP server
│   │
│   ├── memory/
│       ├── server.py                   # Memory MCP server
│
├── data/
│   ├── models/                         # SQLAlchemy DB models
│   │   ├── udahub.py                   # Core DB models (Memory + Mapping)
│   │   ├── cultpass.py                 # External CultPass models
│   │
│   ├── external/                       # External “source-of-truth”
│   │   ├── cultpass_users.jsonl
│   │   ├── cultpass_articles.jsonl
│   │   ├── cultpass_experiences.jsonl
│   │   ├── cultpass.db
│   │
│   ├── core/
│       ├── udahub.db                   # Main core DB
│       ├── memory.db                   # Memory DB
│
├── tests/                              # Full pytest suite
│   ├── conftest.py
│   ├── test_kb_tool.py                 # Tests for KB MCP server
│   ├── test_account_tool.py            # Tests for Account MCP server
│   ├── test_memory_tool.py             # Tests for Memory MCP server
│   ├── test_routing.py                 # Tests for workflow routing logic
│   ├── test_end_to_end.py              # Full end-to-end test of UDA-Hub orchestration
│
├── utils.py                            # Shared utility functions
│
├── dump_mermaid.py                     # utility to draw mermaid diagram of the graph
├── debug_kb_direct.py                  # utility to debug the kb response
├── logger.py                           # utility for logging
├── logs/                               # Full pytest suite
│   ├── uda_hub.jsonl                   # Log file

```

## Setup Instructions
1. Create and activate environment

```
conda create -n uda-hub python=3.11 -y
conda activate uda-hub

```

3. Install dependencies
```
pip install -r requirements.txt

```

4. Configure environment variable

```
touch .env

```
Edit the .env to add key for openai 

```
OPENAI_API_KEY=your_openai_key_here

```

6. Build databases

Run:

* 01_external_db_setup.ipynb

* 02_core_db_setup.ipynb

These create:

* data/external/cultpass.db

* data/core/udahub.db

## Running the App

Run a demo ticket:

```
python 03_agentic_app.py --mode demo

```

Run interactive mode:

```
python 03_agentic_app.py --mode interactive

```

## Running Tests

```
pytest -q

```

You should see the test output as:

```
8 passed in XXs

```

## To inspect structured logs:

```
# Run the demo and show only final workflow completion events
python 03_agentic_app.py --mode demo 2>&1 | grep '"workflow_completed"'

# Show all supervisor decisions
python 03_agentic_app.py --mode demo 2>&1 | grep '"supervisor_decision"'

```
