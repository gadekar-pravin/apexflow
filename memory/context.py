"""ExecutionContextManager -- v2 with DB-backed session persistence.

100% NetworkX Graph-First.  Phase 3 additions:
- _save_session() writes graph to session_store
- load_session() reads from session_store
- _auto_save() triggers _save_session as fire-and-forget task
"""

from __future__ import annotations

import ast
import asyncio
import contextlib
import json
import logging
import time
from datetime import UTC, datetime
from typing import Any

import networkx as nx

from core.event_bus import event_bus
from core.service_registry import ServiceRegistry
from core.stores.session_store import SessionStore

logger = logging.getLogger(__name__)


class ExecutionContextManager:
    def __init__(
        self,
        plan_graph: dict[str, Any],
        session_id: str | None = None,
        original_query: str | None = None,
        file_manifest: list[str] | None = None,
        debug_mode: bool = False,
        api_mode: bool = True,
    ) -> None:
        # Build NetworkX graph with ALL data
        self.plan_graph: nx.DiGraph[str] = nx.DiGraph()

        # Store session metadata in graph attributes
        self.plan_graph.graph["session_id"] = session_id or str(int(time.time()))[-8:]
        self.plan_graph.graph["original_query"] = original_query
        self.plan_graph.graph["file_manifest"] = file_manifest or []
        self.stop_requested = False

        # Async User Input Support
        self.api_mode = api_mode
        self.user_input_event = asyncio.Event()
        self.user_input_value: str | None = None

        self.plan_graph.graph["created_at"] = datetime.now(UTC).isoformat()
        self.plan_graph.graph["status"] = "running"
        self.plan_graph.graph["globals_schema"] = {}

        # Add ROOT node
        self.plan_graph.add_node(
            "ROOT",
            description="Initial Query",
            agent="System",
            status="completed",
            output=None,
            error=None,
            cost=0.0,
            start_time=None,
            end_time=None,
            execution_time=0.0,
        )

        # Build plan DAG
        for node in plan_graph.get("nodes", []):
            node_data: dict[str, Any] = node.copy()
            defaults: dict[str, Any] = {
                "status": "pending",
                "output": None,
                "error": None,
                "cost": 0.0,
                "start_time": None,
                "end_time": None,
                "execution_time": 0.0,
            }
            for k, v in defaults.items():
                node_data.setdefault(k, v)

            self.plan_graph.add_node(node["id"], **node_data)

        for edge in plan_graph.get("edges", []):
            self.plan_graph.add_edge(edge["source"], edge["target"])

        self.debug_mode = debug_mode
        self.service_registry: ServiceRegistry | None = None

    # -- control ------------------------------------------------------------

    def stop(self) -> None:
        """Signal the execution loop to stop."""
        self.stop_requested = True
        self.user_input_event.set()

    def provide_user_input(self, value: str) -> None:
        """Provide input from external source (API)."""
        self.user_input_value = value
        self.user_input_event.set()

    def set_service_registry(self, registry: ServiceRegistry) -> None:
        """Set the ServiceRegistry reference for tool execution."""
        self.service_registry = registry

    # -- graph queries ------------------------------------------------------

    def get_ready_steps(self) -> list[str]:
        """Return all steps whose dependencies are complete and not yet run."""
        ready: list[str] = []

        for node_id in self.plan_graph.nodes:
            node_data = self.plan_graph.nodes[node_id]

            if node_id == "ROOT":
                continue

            status = node_data.get("status", "pending")
            if status in ["completed", "failed", "running", "waiting_input", "stopped", "skipped", "cost_exceeded"]:
                continue

            predecessors = list(self.plan_graph.predecessors(node_id))
            all_deps_complete = all(
                self.plan_graph.nodes[p].get("status", "pending") == "completed" for p in predecessors
            )

            if all_deps_complete:
                ready.append(node_id)

        return ready

    def mark_running(self, step_id: str) -> None:
        """Mark step as running."""
        self.plan_graph.nodes[step_id]["status"] = "running"
        self.plan_graph.nodes[step_id]["start_time"] = datetime.now(UTC).isoformat()
        self._auto_save()

    # -- code detection / extraction ----------------------------------------

    def _has_executable_code(self, output: Any) -> bool:
        """Universal detection of executable code patterns."""
        if not isinstance(output, dict):
            return False
        return (
            "code_variants" in output
            or any(k.startswith("CODE_") for k in output)
            or any(key in output for key in ["tool_calls", "schedule_tool", "browser_commands", "python_code"])
        )

    def _extract_executable_code(self, output: dict[str, Any]) -> dict[str, str]:
        """Extract executable code."""
        code_to_execute: dict[str, str] = {}
        if "code_variants" in output:
            for key, code in output["code_variants"].items():
                if isinstance(code, str):
                    code_to_execute[key] = code.strip()
        return code_to_execute

    def _ensure_parsed_value(self, value: Any) -> Any:
        """Ensure string representations of Python lists/dicts are parsed into actual objects.

        Uses ast.literal_eval (safe -- only evaluates literals, not arbitrary code).
        """
        if not isinstance(value, str):
            if isinstance(value, list):
                return [self._ensure_parsed_value(item) for item in value]
            if isinstance(value, dict):
                return {k: self._ensure_parsed_value(v) for k, v in value.items()}
            return value

        stripped = value.strip()

        if (stripped.startswith("[") and stripped.endswith("]")) or (
            stripped.startswith("{") and stripped.endswith("}")
        ):
            try:
                parsed = json.loads(stripped)
                return self._ensure_parsed_value(parsed)
            except (json.JSONDecodeError, TypeError):
                pass
            try:
                # ast.literal_eval is safe: only evaluates Python literals
                parsed = ast.literal_eval(stripped)  # noqa: S307
                return self._ensure_parsed_value(parsed)
            except (ValueError, SyntaxError):
                pass

        return value

    async def _auto_execute_code(
        self,
        step_id: str,
        output: dict[str, Any],
        input_overrides: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Stub -- code execution is deferred to Phase 4c."""
        return {"status": "skipped", "error": "Deferred to Phase 4c"}

    def _merge_execution_results(self, original_output: Any, execution_result: dict[str, Any]) -> Any:
        """Merge execution results into agent output."""
        if not isinstance(original_output, dict):
            return original_output

        enhanced_output: dict[str, Any] = original_output.copy()
        enhanced_output["execution_result"] = execution_result.get("result")
        enhanced_output["execution_status"] = execution_result.get("status")
        enhanced_output["execution_error"] = execution_result.get("error")
        enhanced_output["execution_time"] = execution_result.get("execution_time")
        enhanced_output["executed_variant"] = execution_result.get("executed_variant")
        enhanced_output["execution_logs"] = execution_result.get("logs")

        if execution_result.get("status") == "success":
            result_data = execution_result.get("result", {})
            if isinstance(result_data, dict):
                for key, value in result_data.items():
                    if key not in enhanced_output:
                        enhanced_output[key] = value

        return enhanced_output

    def _is_clarification_request(self, agent_type: str, output: Any) -> bool:
        """Check if agent output requires user interaction."""
        return agent_type == "ClarificationAgent" and isinstance(output, dict) and "clarificationMessage" in output

    async def _handle_user_interaction(self, clarification_output: dict[str, Any]) -> str | None:
        """Handle user interaction via API (async wait)."""
        message = clarification_output.get("clarificationMessage", "")

        logger.info("Waiting for user input: %s", message)

        self.user_input_event.clear()
        self.user_input_value = None

        self._auto_save()

        while not self.stop_requested:
            try:
                await asyncio.wait_for(self.user_input_event.wait(), timeout=1.0)
                return self.user_input_value
            except TimeoutError:
                continue

        return "Execution stopped by user."

    async def mark_done(
        self,
        step_id: str,
        output: Any = None,
        cost: float | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> None:
        """Mark step as completed with extraction logic."""
        node_data = self.plan_graph.nodes[step_id]
        agent_type: str = node_data.get("agent", "")
        writes: list[str] = node_data.get("writes", [])

        if output and isinstance(output, dict):
            cost = cost if cost is not None else output.get("cost", 0.0)
            input_tokens = input_tokens if input_tokens is not None else output.get("input_tokens", 0)
            output_tokens = output_tokens if output_tokens is not None else output.get("output_tokens", 0)

        # USER INTERACTION CHECK
        if self._is_clarification_request(agent_type, output):
            try:
                node_data["status"] = "waiting_input"
                self._auto_save()
                user_response = await self._handle_user_interaction(output)

                if self.stop_requested:
                    node_data["status"] = "failed"
                    node_data["error"] = "Execution stopped by user during input."
                    self._auto_save()
                    return

                writes_to: str = output.get("writes_to", "user_response")
                rich_context = f"Agent Question: {output.get('clarificationMessage', '')}\nUser Answer: {user_response}"
                self.plan_graph.graph["globals_schema"][writes_to] = rich_context

                output = output.copy()
                output["user_response"] = user_response
                output["rich_context_saved"] = rich_context
                output["interaction_completed"] = True
                logger.info("User input captured: %s", writes_to)
                node_data["status"] = "running"

            except Exception as e:
                logger.exception("User interaction failed: %s", e)
                node_data["error"] = str(e)
                node_data["status"] = "failed"
                node_data["end_time"] = datetime.now(UTC).isoformat()
                self._auto_save()
                return

        # CODE EXECUTION CHECK
        execution_result: dict[str, Any] | None = None
        if self._has_executable_code(output):
            try:
                execution_result = await self._auto_execute_code(step_id, output)
                output = self._merge_execution_results(output, execution_result)
            except Exception as e:
                logger.error("Code execution failed: %s", e)

        # EXTRACTION LOGIC
        globals_schema: dict[str, Any] = self.plan_graph.graph["globals_schema"]

        if writes:
            for write_key in writes:
                extracted = False

                # Strategy 1: From code execution results
                if execution_result and execution_result.get("status") == "success":
                    result_data = execution_result.get("result", {})
                    if write_key in result_data:
                        globals_schema[write_key] = result_data[write_key]
                        extracted = True
                    elif len(result_data) == 1 and len(writes) == 1:
                        _key, value = next(iter(result_data.items()))
                        globals_schema[write_key] = value
                        extracted = True

                # Strategy 2: From direct agent output
                if not extracted and output and isinstance(output, dict):
                    if write_key in output:
                        globals_schema[write_key] = output[write_key]
                        extracted = True
                    elif "output" in output and isinstance(output["output"], dict) and write_key in output["output"]:
                        globals_schema[write_key] = output["output"][write_key]
                        extracted = True
                    elif "final_answer" in output:
                        globals_schema[write_key] = output["final_answer"]
                        extracted = True

                # Strategy 3: Fallback
                if not extracted:
                    logger.warning("Could not extract %s", write_key)
                    globals_schema[write_key] = []

        # Store results
        node_data["status"] = "completed"
        node_data["end_time"] = datetime.now(UTC).isoformat()
        node_data["output"] = output
        node_data["cost"] = cost if cost is not None else 0.0
        node_data["input_tokens"] = input_tokens if input_tokens is not None else 0
        node_data["output_tokens"] = output_tokens if output_tokens is not None else 0
        node_data["total_tokens"] = node_data["input_tokens"] + node_data["output_tokens"]

        if "start_time" in node_data and node_data["start_time"]:
            start = datetime.fromisoformat(node_data["start_time"])
            end = datetime.fromisoformat(node_data["end_time"])
            node_data["execution_time"] = (end - start).total_seconds()

        logger.info("%s completed successfully", step_id)
        self._auto_save()

    def mark_failed(self, step_id: str, error: Exception | str | None = None) -> None:
        """Mark step as failed."""
        node_data = self.plan_graph.nodes[step_id]
        node_data["status"] = "failed"
        node_data["end_time"] = datetime.now(UTC).isoformat()
        node_data["error"] = str(error) if error else None

        if node_data.get("start_time"):
            start = datetime.fromisoformat(node_data["start_time"])
            end = datetime.fromisoformat(node_data["end_time"])
            node_data["execution_time"] = (end - start).total_seconds()

        self._auto_save()

    def get_step_data(self, step_id: str) -> dict[str, Any]:
        """Get all step data from graph."""
        return self.plan_graph.nodes[step_id]  # type: ignore[no-any-return]

    def get_inputs(self, reads: list[str]) -> dict[str, Any]:
        """Get input data from graph globals_schema."""
        inputs: dict[str, Any] = {}
        globals_schema: dict[str, Any] = self.plan_graph.graph["globals_schema"]

        for read_key in reads:
            if read_key in globals_schema:
                inputs[read_key] = globals_schema[read_key]
            else:
                logger.warning("Missing dependency: '%s' not found in globals_schema", read_key)

        return inputs

    def all_done(self) -> bool:
        """Check if all steps are in a terminal state."""
        terminal = {"completed", "failed", "skipped", "stopped", "cost_exceeded"}
        return all(self.plan_graph.nodes[node_id]["status"] in terminal for node_id in self.plan_graph.nodes)

    def get_execution_summary(self) -> dict[str, Any]:
        """Get execution summary with cost and token breakdown."""
        completed = sum(
            1
            for node_id in self.plan_graph.nodes
            if node_id != "ROOT" and self.plan_graph.nodes[node_id].get("status") == "completed"
        )
        failed = sum(
            1
            for node_id in self.plan_graph.nodes
            if node_id != "ROOT" and self.plan_graph.nodes[node_id].get("status") == "failed"
        )
        total = len(self.plan_graph.nodes) - 1

        total_cost = 0.0
        total_input_tokens = 0
        total_output_tokens = 0
        cost_breakdown: dict[str, dict[str, Any]] = {}

        for node_id in self.plan_graph.nodes:
            if node_id != "ROOT":
                node_data = self.plan_graph.nodes[node_id]
                node_cost: float = node_data.get("cost", 0.0)
                node_input_tokens: int = node_data.get("input_tokens", 0)
                node_output_tokens: int = node_data.get("output_tokens", 0)

                if node_cost > 0:
                    agent: str = node_data.get("agent", "Unknown")
                    cost_breakdown[f"{node_id} ({agent})"] = {
                        "cost": node_cost,
                        "input_tokens": node_input_tokens,
                        "output_tokens": node_output_tokens,
                    }

                total_cost += node_cost
                total_input_tokens += node_input_tokens
                total_output_tokens += node_output_tokens

        final_outputs: dict[str, Any] = {}
        all_reads: set[str] = set()
        all_writes: set[str] = set()

        for node_id in self.plan_graph.nodes:
            node_data = self.plan_graph.nodes[node_id]
            all_reads.update(node_data.get("reads", []))
            all_writes.update(node_data.get("writes", []))

        final_write_keys = all_writes - all_reads
        globals_schema: dict[str, Any] = self.plan_graph.graph["globals_schema"]
        for key in final_write_keys:
            if key in globals_schema:
                final_outputs[key] = globals_schema[key]

        return {
            "session_id": self.plan_graph.graph["session_id"],
            "original_query": self.plan_graph.graph["original_query"],
            "completed_steps": completed,
            "failed_steps": failed,
            "total_steps": total,
            "total_cost": total_cost,
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_tokens": total_input_tokens + total_output_tokens,
            "cost_breakdown": cost_breakdown,
            "final_outputs": final_outputs,
            "globals_schema": globals_schema,
        }

    def set_file_profiles(self, file_profiles: dict[str, Any]) -> None:
        """Store file profiles in graph attributes."""
        self.plan_graph.graph["file_profiles"] = file_profiles

    def _auto_save(self) -> None:
        """Persist graph to DB and emit event_bus event."""
        if self.debug_mode:
            return
        with contextlib.suppress(RuntimeError):
            loop = asyncio.get_running_loop()
            loop.create_task(self._save_session())
            loop.create_task(
                event_bus.publish(
                    "context_updated",
                    "ExecutionContextManager",
                    {"session_id": self.plan_graph.graph["session_id"]},
                )
            )

    async def _save_session(self, user_id: str = "dev-user") -> None:
        """Persist graph data to session_store."""
        try:
            store = SessionStore()
            session_id = self.plan_graph.graph.get("session_id", "")
            if not session_id:
                return
            graph_data = nx.node_link_data(self.plan_graph, edges="edges")
            node_outputs: dict[str, Any] = {}
            for node_id in self.plan_graph.nodes:
                nd = self.plan_graph.nodes[node_id]
                if nd.get("output"):
                    node_outputs[node_id] = nd["output"]
            await store.update_graph(user_id, session_id, graph_data, node_outputs)
        except Exception as e:
            logger.debug("_save_session failed (non-fatal): %s", e)

    @classmethod
    async def load_session(cls, user_id: str, session_id: str) -> ExecutionContextManager | None:
        """Load a session from the DB and reconstruct the context."""
        store = SessionStore()
        session = await store.get(user_id, session_id)
        if not session:
            return None
        graph_data = session.get("graph_data", {})
        if not graph_data or not isinstance(graph_data, dict):
            return None
        try:
            g = nx.node_link_graph(graph_data, edges="edges")
            ctx = cls.__new__(cls)
            ctx.plan_graph = g
            ctx.stop_requested = False
            ctx.api_mode = True
            ctx.user_input_event = asyncio.Event()
            ctx.user_input_value = None
            ctx.debug_mode = False
            ctx.service_registry = None
            return ctx
        except Exception as e:
            logger.error("Failed to load session %s: %s", session_id, e)
            return None
