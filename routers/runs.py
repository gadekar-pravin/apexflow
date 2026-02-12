"""Runs router -- v2 port from v1, DB-backed via SessionStore.

Replaces filesystem session I/O with session_store partial updates.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import networkx as nx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from core.auth import get_user_id
from core.graph_adapter import nx_to_reactflow
from core.stores.session_store import SessionStore
from shared.state import active_loops, get_service_registry

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/runs", tags=["Runs"])

_session_store = SessionStore()


# -- models -------------------------------------------------------------------


class RunRequest(BaseModel):
    query: str
    agent_type: str | None = None


class RunResponse(BaseModel):
    id: str
    status: str
    created_at: str
    query: str


class UserInputRequest(BaseModel):
    node_id: str
    response: str


# -- background task ----------------------------------------------------------


async def process_run(
    run_id: str,
    query: str,
    *,
    user_id: str = "dev-user",
) -> dict[str, Any]:
    """Background task to execute the agent loop."""
    context = None
    run_status = "completed"
    try:
        from core.loop import AgentLoop4

        registry = get_service_registry()
        loop = AgentLoop4(service_registry=registry)
        active_loops[run_id] = loop

        await _session_store.update_status(user_id, run_id, "running")

        context = await loop.run(query, [], {}, [], session_id=run_id, user_id=user_id)

        # Save graph data
        if context and context.plan_graph:
            graph_data = nx.node_link_data(context.plan_graph, edges="edges")
            node_outputs: dict[str, Any] = {}
            total_cost = 0.0
            for node_id in context.plan_graph.nodes:
                nd = context.plan_graph.nodes[node_id]
                if nd.get("output"):
                    node_outputs[node_id] = nd["output"]
                total_cost += nd.get("cost", 0.0)

            await _session_store.update_graph(user_id, run_id, graph_data, node_outputs)
            if total_cost > 0:
                await _session_store.update_cost(user_id, run_id, total_cost)

            # Determine final status
            has_failed = any(
                context.plan_graph.nodes[n].get("status") == "failed" for n in context.plan_graph.nodes if n != "ROOT"
            )
            run_status = "failed" if has_failed else "completed"
            error_msg = None
            if has_failed:
                for n in context.plan_graph.nodes:
                    nd = context.plan_graph.nodes[n]
                    if nd.get("status") == "failed" and nd.get("error"):
                        error_msg = str(nd["error"])
                        break
            await _session_store.update_status(user_id, run_id, run_status, error=error_msg)
        else:
            await _session_store.update_status(user_id, run_id, "completed")

    except Exception as e:
        logger.error("Run %s failed: %s", run_id, e)
        run_status = "failed"
        await _session_store.update_status(user_id, run_id, "failed", error=str(e))
    finally:
        active_loops.pop(run_id, None)

    # Build return result
    final_result: dict[str, Any] = {"status": run_status, "run_id": run_id}
    if context and context.plan_graph:
        summary = context.get_execution_summary()
        final_result["summary"] = summary.get("final_outputs", {})
    return final_result


# -- endpoints ----------------------------------------------------------------


@router.post("/execute")
async def create_run(
    request: RunRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    run_id = uuid.uuid4().hex[:12]
    now = datetime.now(UTC).isoformat()

    await _session_store.create(
        user_id,
        run_id,
        request.query,
        agent_type=request.agent_type,
    )

    background_tasks.add_task(process_run, run_id, request.query, user_id=user_id)

    return {"id": run_id, "status": "starting", "created_at": now, "query": request.query}


@router.get("")
async def list_runs(
    user_id: str = Depends(get_user_id),
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    return await _session_store.list_sessions(user_id, limit=limit, offset=offset)


@router.get("/{run_id}")
async def get_run(
    run_id: str,
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    # Check active loops first (verify ownership via session store)
    if run_id in active_loops:
        session = await _session_store.get(user_id, run_id)
        if not session:
            raise HTTPException(status_code=404, detail="Run not found")
        loop = active_loops[run_id]
        if loop.context and loop.context.plan_graph:
            live_flow = nx_to_reactflow(loop.context.plan_graph)
            return {"id": run_id, "status": "running", "graph": live_flow}

    # Check DB
    session = await _session_store.get(user_id, run_id)
    if not session:
        raise HTTPException(status_code=404, detail="Run not found")

    graph_data = session.get("graph_data")
    react_flow: dict[str, list[dict[str, Any]]] | None = None
    if graph_data:
        # asyncpg may return JSONB as str in some environments
        if isinstance(graph_data, str):
            try:
                graph_data = json.loads(graph_data)
            except (json.JSONDecodeError, TypeError):
                graph_data = None
        if isinstance(graph_data, dict) and graph_data.get("nodes"):
            try:
                g = nx.node_link_graph(graph_data, edges="edges")
                react_flow = nx_to_reactflow(g)
            except Exception:
                logger.exception("Failed to convert graph for run %s", run_id)

    return {
        "id": run_id,
        "status": session.get("status", "unknown"),
        "query": session.get("query", ""),
        "cost": float(session.get("cost", 0)),
        "created_at": session["created_at"].isoformat() if session.get("created_at") else None,
        "completed_at": session["completed_at"].isoformat() if session.get("completed_at") else None,
        "graph": react_flow,
    }


@router.post("/{run_id}/input")
async def provide_input(
    run_id: str,
    request: UserInputRequest,
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    if run_id not in active_loops:
        raise HTTPException(status_code=404, detail="Active run not found")

    # Ownership check
    session = await _session_store.get(user_id, run_id)
    if not session:
        raise HTTPException(status_code=404, detail="Run not found")

    loop = active_loops[run_id]
    if not loop.context:
        raise HTTPException(status_code=400, detail="Context not initialized")

    loop.context.provide_user_input(request.response)
    return {"id": run_id, "status": "input_received"}


@router.post("/{run_id}/stop")
async def stop_run(
    run_id: str,
    user_id: str = Depends(get_user_id),
) -> dict[str, Any]:
    if run_id not in active_loops:
        raise HTTPException(status_code=404, detail="Active run not found")

    # Ownership check
    session = await _session_store.get(user_id, run_id)
    if not session:
        raise HTTPException(status_code=404, detail="Run not found")

    loop = active_loops[run_id]
    loop.stop()
    await _session_store.update_status(user_id, run_id, "cancelled")
    return {"id": run_id, "status": "stopping"}


@router.delete("/{run_id}")
async def delete_run(
    run_id: str,
    user_id: str = Depends(get_user_id),
) -> dict[str, str]:
    loop = active_loops.pop(run_id, None)
    if loop:
        loop.stop()

    await _session_store.delete(user_id, run_id)
    return {"id": run_id, "status": "deleted"}
