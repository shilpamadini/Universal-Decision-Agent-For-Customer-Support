from agentic.workflow import orchestrator

if __name__ == "__main__":
    graph = orchestrator.get_graph()

    mermaid = graph.draw_mermaid()

    print(mermaid)
