from __future__ import annotations

import json
from typing import Any

import networkx as nx


def _extract_output(output: Any) -> str:
    """
    Extract and properly serialize output from agent nodes.
    Handles nested dicts, lists, and strings properly.
    """
    if output is None:
        return ""

    if isinstance(output, str):
        return output

    if isinstance(output, dict | list | tuple):
        return json.dumps(output)

    # Fallback to string representation
    return str(output)


def nx_to_reactflow(graph: nx.DiGraph) -> dict[str, list[dict[str, Any]]]:
    """
    Convert a NetworkX graph to ReactFlow nodes and edges.
    """
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    # Calculate layout: Simple hierarchical (DAG) layout
    pos: dict[str, dict[str, float]] = {}

    # Simple Topological-like generation for Y-axis, spread for X-axis
    try:
        layers = list(nx.topological_generations(graph))

        for y_idx, layer in enumerate(layers):
            layer_width = len(layer) * 300
            start_x = -(layer_width / 2)

            for x_idx, node_id in enumerate(layer):
                pos[node_id] = {"x": start_x + (x_idx * 300), "y": y_idx * 200}
    except Exception:
        # Fallback to spring layout if not DAG or error
        spring_pos = nx.spring_layout(graph, scale=500, seed=42)
        for node_id, p in spring_pos.items():
            pos[node_id] = {"x": p[0] * 500, "y": p[1] * 500}

    # Resolve input values from globals_schema for each node
    globals_schema: dict[str, Any] = graph.graph.get("globals_schema", {})

    for node_id, data in graph.nodes(data=True):
        status = data.get("status", "pending")
        agent_type = data.get("agent", data.get("agent_type", "Generic"))
        if node_id == "ROOT" or agent_type == "System":
            agent_type = "PlannerAgent"

        p = pos.get(node_id, {"x": 0, "y": 0})

        # Resolve actual input values from globals_schema using reads keys
        reads = data.get("reads", [])
        inputs: dict[str, Any] = {}
        for key in reads:
            if key in globals_schema:
                inputs[key] = globals_schema[key]

        nodes.append(
            {
                "id": str(node_id),
                "type": "agentNode",
                "position": p,
                "data": {
                    "label": agent_type or str(node_id),
                    "type": agent_type,
                    "status": status,
                    "description": data.get("description", ""),
                    "prompt": data.get("agent_prompt") or data.get("prompt") or data.get("description") or "",
                    "reads": reads,
                    "writes": data.get("writes", []),
                    "inputs": inputs,
                    "cost": data.get("cost", 0.0),
                    "execution_time": data.get("execution_time", 0.0),
                    "input_tokens": data.get("input_tokens", 0),
                    "output_tokens": data.get("output_tokens", 0),
                    "total_tokens": data.get("total_tokens", 0),
                    "start_time": data.get("start_time"),
                    "end_time": data.get("end_time"),
                    "output": _extract_output(data.get("output")),
                    "error": str(data.get("error", "")) if data.get("error") else "",
                    "execution_result": data.get("execution_result"),
                    "iterations": data.get("iterations", []),
                    "logs": data.get("logs", []),
                    "execution_logs": data.get("execution_logs", ""),
                    "calls": data.get("calls", []),
                },
            }
        )

    for u, v in graph.edges():
        edges.append(
            {
                "id": f"e{u}-{v}",
                "source": str(u),
                "target": str(v),
                "type": "custom",
                "animated": False,
                "style": {"stroke": "#888888", "strokeDasharray": "none"},
            }
        )

    return {"nodes": nodes, "edges": edges}
