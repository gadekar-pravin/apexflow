"""AgentLoop4 – v2 with ServiceRegistry, no Rich/visualizer.

Changes from v1:
- Removed ui.visualizer, rich.live, rich.console imports
- Replaced all console.print/visualizer.* with logging
- Replaced self.multi_mcp → self.service_registry
- Replaced self.context.multi_mcp → self.context.set_service_registry(...)
- Replaced self.context._save_session() → self.context._auto_save()
- Tool call results are raw Python objects (not MCP CallToolResult)
- Single error translation point for tool calls using ToolNotFoundError/ToolExecutionError
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from agents.base_agent import AgentRunner
from core.event_bus import event_bus
from core.service_registry import ServiceRegistry, ToolExecutionError, ToolNotFoundError
from core.tool_context import ToolContext
from core.utils import log_error, log_step
from memory.context import ExecutionContextManager

logger = logging.getLogger(__name__)


# ===== EXPONENTIAL BACKOFF FOR TRANSIENT FAILURES =====


async def retry_with_backoff(
    async_func: Any,
    max_retries: int = 3,
    base_delay: float = 1.0,
    retryable_errors: tuple[type[BaseException], ...] | None = None,
) -> Any:
    """Retry an async function with exponential backoff."""
    if retryable_errors is None:
        retryable_errors = (
            asyncio.TimeoutError,
            ConnectionError,
            TimeoutError,
        )

    last_exception: BaseException | None = None

    for attempt in range(max_retries):
        try:
            return await async_func()
        except retryable_errors as e:
            last_exception = e
            if attempt < max_retries - 1:
                delay = base_delay * (2**attempt)
                log_step(
                    f"Transient error: {type(e).__name__}. Retrying in {delay}s (attempt {attempt + 1}/{max_retries})"
                )
                await asyncio.sleep(delay)
            else:
                log_error(f"All {max_retries} retry attempts failed: {e}")
        except Exception:
            raise

    if last_exception is not None:
        raise last_exception
    msg = f"retry_with_backoff exhausted {max_retries} attempts without capturing an exception"
    raise RuntimeError(msg)


class AgentLoop4:
    def __init__(self, service_registry: ServiceRegistry, strategy: str = "conservative") -> None:
        self.service_registry = service_registry
        self.strategy = strategy
        self.agent_runner = AgentRunner(service_registry)
        self.context: ExecutionContextManager | None = None
        self._tasks: set[asyncio.Task[Any]] = set()

    def stop(self) -> None:
        """Request execution stop."""
        if self.context:
            self.context.stop()
        for t in list(self._tasks):
            if not t.done():
                t.cancel()

    async def _track_task(self, coro_or_future: Any) -> Any:
        """Track an async task so it can be cancelled on stop()."""
        task: asyncio.Task[Any] = (
            asyncio.create_task(coro_or_future) if asyncio.iscoroutine(coro_or_future) else coro_or_future
        )

        self._tasks.add(task)
        try:
            return await task
        except asyncio.CancelledError:
            raise
        finally:
            self._tasks.discard(task)

    async def run(
        self,
        query: str,
        file_manifest: list[str],
        globals_schema: dict[str, Any],
        uploaded_files: list[str],
        session_id: str | None = None,
        memory_context: Any = None,
    ) -> ExecutionContextManager | None:
        """Main execution entry point."""
        # PHASE 0: BOOTSTRAP CONTEXT
        bootstrap_graph: dict[str, Any] = {
            "nodes": [
                {
                    "id": "Query",
                    "description": "Formulate execution plan",
                    "agent": "PlannerAgent",
                    "status": "running",
                    "reads": ["original_query"],
                    "writes": ["plan_graph"],
                }
            ],
            "edges": [{"source": "ROOT", "target": "Query"}],
        }

        try:
            self.context = ExecutionContextManager(
                bootstrap_graph,
                session_id=session_id,
                original_query=query,
                file_manifest=file_manifest,
            )
            self.context.memory_context = memory_context  # type: ignore[attr-defined]
            self.context.set_service_registry(self.service_registry)
            self.context.plan_graph.graph["globals_schema"].update(globals_schema)
            self.context._auto_save()
            log_step("Session initialized with Query processing")
        except Exception as e:
            logger.error("ERROR initializing context: %s", e)
            raise

        # Phase 1: File Profiling
        file_profiles: dict[str, Any] = {}
        if uploaded_files:

            async def run_distiller() -> dict[str, Any]:
                return await self.agent_runner.run_agent(
                    "DistillerAgent",
                    {
                        "task": "profile_files",
                        "files": uploaded_files,
                        "instruction": "Profile and summarize each file's structure, columns, content type",
                        "writes": ["file_profiles"],
                    },
                )

            file_result: dict[str, Any] = await self._track_task(retry_with_backoff(run_distiller))
            if file_result["success"]:
                file_profiles = file_result["output"]
                self.context.set_file_profiles(file_profiles)

        # Phase 2: Planning and Execution Loop
        try:
            while True:
                if self.context.stop_requested:
                    break

                # Capture context in a local variable to avoid union-attr issues
                ctx = self.context

                async def run_planner(_ctx: ExecutionContextManager = ctx) -> dict[str, Any]:
                    return await self.agent_runner.run_agent(
                        "PlannerAgent",
                        {
                            "original_query": query,
                            "planning_strategy": self.strategy,
                            "globals_schema": _ctx.plan_graph.graph.get("globals_schema", {}),
                            "file_manifest": file_manifest,
                            "file_profiles": file_profiles,
                            "memory_context": memory_context,
                        },
                    )

                plan_result: dict[str, Any] = await self._track_task(retry_with_backoff(run_planner))

                if self.context.stop_requested:
                    break

                if not plan_result["success"]:
                    self.context.mark_failed("Query", plan_result["error"])
                    raise RuntimeError(f"Planning failed: {plan_result['error']}")

                if "plan_graph" not in plan_result["output"]:
                    self.context.mark_failed("Query", "Output missing plan_graph")
                    raise RuntimeError("PlannerAgent output missing 'plan_graph' key.")

                # AUTO-CLARIFICATION CHECK
                AUTO_CLARIFY_THRESHOLD = 0.7
                confidence = plan_result["output"].get("interpretation_confidence", 1.0)
                ambiguity_notes = plan_result["output"].get("ambiguity_notes", [])

                plan_nodes = plan_result["output"]["plan_graph"].get("nodes", [])
                has_clarification_agent = any(n.get("agent") == "ClarificationAgent" for n in plan_nodes)

                if confidence < AUTO_CLARIFY_THRESHOLD and ambiguity_notes and not has_clarification_agent:
                    log_step(f"Low confidence ({confidence:.2f}), auto-triggering clarification")

                    first_step = plan_result["output"].get("next_step_id", "T001")
                    clarification_write_key = "user_clarification_T000"

                    clarification_node = {
                        "id": "T000_AutoClarify",
                        "agent": "ClarificationAgent",
                        "description": "Clarify ambiguous requirements before proceeding",
                        "agent_prompt": (
                            f"The system has identified ambiguities in the user's request. "
                            f"Please ask for clarification on: {'; '.join(ambiguity_notes)}"
                        ),
                        "reads": [],
                        "writes": [clarification_write_key],
                        "status": "pending",
                    }

                    plan_result["output"]["plan_graph"]["nodes"].insert(0, clarification_node)
                    plan_result["output"]["plan_graph"]["edges"].insert(
                        0, {"source": "T000_AutoClarify", "target": first_step}
                    )

                    for node in plan_result["output"]["plan_graph"]["nodes"]:
                        if node.get("id") == first_step:
                            if "reads" not in node:
                                node["reads"] = []
                            if clarification_write_key not in node["reads"]:
                                node["reads"].append(clarification_write_key)
                                log_step(f"Wired {clarification_write_key} into {first_step}'s reads")
                            break

                    plan_result["output"]["next_step_id"] = "T000_AutoClarify"
                    log_step(f"Injected ClarificationAgent before {first_step}")
                elif has_clarification_agent:
                    log_step("Planner already added ClarificationAgent, skipping auto-injection")

                # Mark Query/Planner as Done
                planner_output = plan_result["output"]
                self.context.plan_graph.nodes["Query"]["output"] = planner_output
                self.context.plan_graph.nodes["Query"]["status"] = "completed"
                self.context.plan_graph.nodes["Query"]["end_time"] = datetime.now(UTC).isoformat()
                if isinstance(planner_output, dict):
                    self.context.plan_graph.nodes["Query"]["cost"] = planner_output.get("cost", 0.0)
                    self.context.plan_graph.nodes["Query"]["input_tokens"] = planner_output.get("input_tokens", 0)
                    self.context.plan_graph.nodes["Query"]["output_tokens"] = planner_output.get("output_tokens", 0)
                    self.context.plan_graph.nodes["Query"]["total_tokens"] = planner_output.get("total_tokens", 0)

                # PHASE 3: EXPAND GRAPH
                new_plan_graph = plan_result["output"]["plan_graph"]
                self._merge_plan_into_context(new_plan_graph)

                try:
                    await self._track_task(self._execute_dag(self.context))

                    if self.context.stop_requested:
                        break

                    if self._should_replan():
                        log_step("Adaptive Re-planning: Clarification resolved, formulating next steps...")
                        self.context.plan_graph.nodes["Query"]["status"] = "running"
                        self.context._auto_save()
                        continue
                    else:
                        return self.context

                except (Exception, asyncio.CancelledError) as e:
                    if isinstance(e, asyncio.CancelledError) or self.context.stop_requested:
                        log_step("Execution interrupted/stopped.")
                        break
                    logger.error("ERROR during execution: %s", e, exc_info=True)
                    raise

        except (Exception, asyncio.CancelledError) as e:
            if self.context:
                final_status = (
                    "stopped" if (self.context.stop_requested or isinstance(e, asyncio.CancelledError)) else "failed"
                )
                for node_id in self.context.plan_graph.nodes:
                    if self.context.plan_graph.nodes[node_id].get("status") in ["running", "pending"]:
                        self.context.plan_graph.nodes[node_id]["status"] = final_status
                        if final_status == "failed":
                            self.context.plan_graph.nodes[node_id]["error"] = str(e)

                self.context.plan_graph.graph["status"] = final_status
                if final_status == "failed":
                    self.context.plan_graph.graph["error"] = str(e)
                self.context._auto_save()
            if not isinstance(e, asyncio.CancelledError) and not (self.context and self.context.stop_requested):
                raise
            return self.context

        return self.context

    def _should_replan(self) -> bool:
        """Check if graph needs expansion (re-planning)."""
        assert self.context is not None
        if not self.context.all_done():
            return False

        for node_id, node_data in self.context.plan_graph.nodes(data=True):
            if (
                node_data.get("agent") == "ClarificationAgent"
                and node_data.get("status") == "completed"
                and not list(self.context.plan_graph.successors(node_id))
            ):
                return True

        return False

    def _merge_plan_into_context(self, new_plan_graph: dict[str, Any]) -> None:
        """Merge planned nodes into the existing bootstrap context."""
        assert self.context is not None
        new_nodes: list[dict[str, Any]] = new_plan_graph.get("nodes", [])
        new_edges: list[dict[str, Any]] = new_plan_graph.get("edges", [])

        nodes_with_incoming_edges: set[str] = set()

        for node in new_nodes:
            node_data = node.copy()
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

            if node["id"] in self.context.plan_graph:
                existing_status = self.context.plan_graph.nodes[node["id"]].get("status")
                if existing_status == "completed":
                    continue

            self.context.plan_graph.add_node(node["id"], **node_data)

        for edge in new_edges:
            source = edge.get("source") or edge.get("from")
            target = edge.get("target") or edge.get("to")

            if not source or not target:
                log_step(f"Skipping malformed edge: {edge}")
                continue

            if source == "ROOT":
                source = "Query"

            self.context.plan_graph.add_edge(source, target)
            nodes_with_incoming_edges.add(target)

        for node in new_nodes:
            if node["id"] not in nodes_with_incoming_edges:
                log_step(f"Auto-connected orphan node {node['id']} to Query")
                self.context.plan_graph.add_edge("Query", node["id"])

        # Safety net: wire ClarificationAgent outputs to successor nodes
        for node in new_nodes:
            if node.get("agent") == "ClarificationAgent":
                clarification_node_id = node["id"]
                clarification_writes: list[str] = node.get("writes", [])

                if not clarification_writes:
                    continue

                for edge in new_edges:
                    if edge.get("source") == clarification_node_id:
                        successor_id = edge.get("target")
                        if not successor_id:
                            continue

                        for succ_node in new_nodes:
                            if succ_node.get("id") == successor_id:
                                if "reads" not in succ_node:
                                    succ_node["reads"] = []

                                for write_key in clarification_writes:
                                    if write_key not in succ_node["reads"]:
                                        succ_node["reads"].append(write_key)
                                        log_step(f"Auto-wired {write_key} into {successor_id}'s reads")

                                        if successor_id in self.context.plan_graph:
                                            if "reads" not in self.context.plan_graph.nodes[successor_id]:
                                                self.context.plan_graph.nodes[successor_id]["reads"] = []
                                            if write_key not in self.context.plan_graph.nodes[successor_id]["reads"]:
                                                self.context.plan_graph.nodes[successor_id]["reads"].append(write_key)
                                break

        self.context._auto_save()
        log_step("Plan merged into execution context")

    async def _execute_dag(self, context: ExecutionContextManager) -> None:
        """Execute DAG steps in dependency order."""
        # Cost threshold enforcement
        from config.settings_loader import reload_settings

        settings = reload_settings()
        max_cost: float = settings.get("agent", {}).get("max_cost_per_run", 0.50)
        warn_cost: float = settings.get("agent", {}).get("warn_at_cost", 0.25)
        cost_warning_shown = False

        while not context.all_done():
            if context.stop_requested:
                logger.info("Aborting execution: cleaning up nodes...")
                for n_id in context.plan_graph.nodes:
                    if context.plan_graph.nodes[n_id].get("status") == "running":
                        context.plan_graph.nodes[n_id]["status"] = "stopped"
                context._auto_save()
                break

            ready_steps = context.get_ready_steps()
            ready_steps = [s for s in ready_steps if context.plan_graph.nodes[s]["status"] == "pending"]

            if not ready_steps:
                running_or_waiting = any(
                    context.plan_graph.nodes[n]["status"] in ["running", "waiting_input"]
                    for n in context.plan_graph.nodes
                )

                if not running_or_waiting:
                    # Mark pending nodes whose predecessors failed as skipped
                    stuck = False
                    for n_id in context.plan_graph.nodes:
                        if context.plan_graph.nodes[n_id].get("status") != "pending":
                            continue
                        preds = list(context.plan_graph.predecessors(n_id))
                        if any(
                            context.plan_graph.nodes[p].get("status") in ["failed", "skipped", "cost_exceeded"]
                            for p in preds
                        ):
                            context.plan_graph.nodes[n_id]["status"] = "skipped"
                            context.plan_graph.nodes[n_id]["error"] = "Skipped: dependency failed"
                            log_step(f"Skipped {n_id}: dependency failed")
                            stuck = True
                    if stuck:
                        context._auto_save()
                        continue  # re-evaluate with newly skipped nodes

                    is_complete = all(
                        context.plan_graph.nodes[n]["status"] in ["completed", "failed", "skipped", "cost_exceeded"]
                        for n in context.plan_graph.nodes
                        if n != "ROOT"
                    )
                    if is_complete:
                        break

                await asyncio.sleep(0.5)
                continue

            # Mark running
            for step_id in ready_steps:
                context.mark_running(step_id)

            # Execute agents
            tasks: list[Any] = []
            for step_id in ready_steps:
                step_data = context.get_step_data(step_id)
                desc = step_data.get("agent_prompt", step_data.get("description", "No description"))[:60]
                log_step(f"Starting {step_id} ({step_data['agent']}): {desc}...")
                tasks.append(self._track_task(self._execute_step(step_id, context)))

            results: list[Any] = await self._track_task(asyncio.gather(*tasks, return_exceptions=True))

            MAX_STEP_RETRIES = 2

            for step_id, result in zip(ready_steps, results, strict=True):
                step_data = context.get_step_data(step_id)
                retry_count = step_data.get("_retry_count", 0)

                # Handle awaiting input
                if isinstance(result, dict) and result.get("status") == "waiting_input":
                    context.plan_graph.nodes[step_id]["status"] = "waiting_input"
                    if "output" in result:
                        context.plan_graph.nodes[step_id]["output"] = result["output"]
                    context._auto_save()
                    log_step(f"{step_id}: Waiting for user input...")
                    continue

                session_id = context.plan_graph.graph.get("session_id", "")

                if isinstance(result, Exception):
                    if retry_count < MAX_STEP_RETRIES:
                        step_data["_retry_count"] = retry_count + 1
                        context.plan_graph.nodes[step_id]["status"] = "pending"
                        log_step(f"Retrying {step_id} (attempt {retry_count + 1}/{MAX_STEP_RETRIES}): {result!s}")
                    else:
                        context.mark_failed(step_id, str(result))
                        log_error(f"Failed {step_id} after {MAX_STEP_RETRIES} retries: {result!s}")
                        await event_bus.publish(
                            "step_failed",
                            "AgentLoop4",
                            {
                                "step_id": step_id,
                                "session_id": session_id,
                                "agent_type": step_data.get("agent", ""),
                                "error": str(result),
                            },
                        )
                elif result["success"]:
                    await context.mark_done(step_id, result["output"])
                    log_step(f"Completed {step_id} ({step_data['agent']})")
                    node_data = context.plan_graph.nodes[step_id]
                    await event_bus.publish(
                        "step_complete",
                        "AgentLoop4",
                        {
                            "step_id": step_id,
                            "session_id": session_id,
                            "agent_type": step_data.get("agent", ""),
                            "execution_time": node_data.get("execution_time", 0),
                            "cost": node_data.get("cost", 0),
                        },
                    )
                else:
                    if retry_count < MAX_STEP_RETRIES:
                        step_data["_retry_count"] = retry_count + 1
                        context.plan_graph.nodes[step_id]["status"] = "pending"
                        log_step(
                            f"Retrying {step_id} (attempt {retry_count + 1}/{MAX_STEP_RETRIES}): {result['error']}"
                        )
                    else:
                        context.mark_failed(step_id, result["error"])
                        log_error(f"Failed {step_id} after {MAX_STEP_RETRIES} retries: {result['error']}")
                        await event_bus.publish(
                            "step_failed",
                            "AgentLoop4",
                            {
                                "step_id": step_id,
                                "session_id": session_id,
                                "agent_type": step_data.get("agent", ""),
                                "error": result["error"],
                            },
                        )

            # Cost threshold check
            accumulated_cost = sum(
                context.plan_graph.nodes[n].get("cost", 0)
                for n in context.plan_graph.nodes
                if context.plan_graph.nodes[n].get("status") == "completed"
            )

            if not cost_warning_shown and accumulated_cost >= warn_cost:
                log_step(f"Cost Warning: ${accumulated_cost:.4f} (threshold: ${warn_cost:.2f})")
                cost_warning_shown = True

            if accumulated_cost >= max_cost:
                log_error(f"Cost Exceeded: ${accumulated_cost:.4f} > ${max_cost:.2f}")
                context.plan_graph.graph["status"] = "cost_exceeded"
                context.plan_graph.graph["final_cost"] = accumulated_cost
                break

        # Final status (preserve cost_exceeded if already set)
        if context.plan_graph.graph.get("status") == "cost_exceeded":
            pass
        elif context.stop_requested:
            context.plan_graph.graph["status"] = "stopped"
        elif any(context.plan_graph.nodes[n]["status"] == "failed" for n in context.plan_graph.nodes):
            context.plan_graph.graph["status"] = "failed"
        elif context.all_done():
            context.plan_graph.graph["status"] = "completed"
        else:
            context.plan_graph.graph["status"] = "failed"

        context._auto_save()

        if context.all_done():
            logger.info("All tasks completed!")

    async def _execute_step(self, step_id: str, context: ExecutionContextManager) -> dict[str, Any]:
        """Execute a single step with ReAct tool-calling loop."""
        session_id = context.plan_graph.graph.get("session_id", "")
        await event_bus.publish(
            "step_start",
            "AgentLoop4",
            {"step_id": step_id, "session_id": session_id},
        )
        step_data = context.get_step_data(step_id)
        agent_type = step_data["agent"]

        inputs = context.get_inputs(step_data.get("reads", []))

        def build_agent_input(
            instruction: str | None = None,
            previous_output: dict[str, Any] | None = None,
            iteration_context: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            payload: dict[str, Any] = {
                "step_id": step_id,
                "agent_prompt": instruction or step_data.get("agent_prompt", step_data["description"]),
                "reads": step_data.get("reads", []),
                "writes": step_data.get("writes", []),
                "inputs": inputs,
                "original_query": context.plan_graph.graph["original_query"],
                "session_context": {
                    "session_id": context.plan_graph.graph["session_id"],
                    "created_at": context.plan_graph.graph["created_at"],
                    "file_manifest": context.plan_graph.graph["file_manifest"],
                    "memory_context": getattr(context, "memory_context", None),
                },
                **({"previous_output": previous_output} if previous_output else {}),
                **({"iteration_context": iteration_context} if iteration_context else {}),
            }

            if agent_type == "FormatterAgent":
                payload["all_globals_schema"] = context.plan_graph.graph["globals_schema"].copy()

            return payload

        # ReAct Loop (max 15 turns)
        max_turns = 15
        current_input = build_agent_input()
        iterations_data: list[dict[str, Any]] = []

        for turn in range(1, max_turns + 1):
            log_step(f"{agent_type} Iteration {turn}/{max_turns}")

            # Bind current_input to avoid B023 (closure capturing loop variable)
            bound_input = current_input

            async def run_agent_step(_input: dict[str, Any] = bound_input) -> dict[str, Any]:
                return await self.agent_runner.run_agent(agent_type, _input)

            try:
                result: dict[str, Any] = await retry_with_backoff(run_agent_step)
            except Exception as e:
                return {"success": False, "error": f"Agent failed after retries: {e!s}"}

            if not result["success"]:
                return result

            output = result["output"]

            # Check for clarification request — route through mark_done
            # so it awaits user input and writes the response into globals_schema.
            if output.get("clarificationMessage"):
                await context.mark_done(step_id, output)
                return {"success": True, "output": output}

            iterations_data.append({"iteration": turn, "output": output})

            if context.stop_requested:
                log_step(f"{agent_type}: Stop requested, aborting iteration {turn}")
                return {"success": False, "error": "Stop requested"}

            step_data = context.get_step_data(step_id)
            step_data["iterations"] = iterations_data

            # 1. Check for 'call_tool' (ReAct)
            if output.get("call_tool"):
                tool_call = output["call_tool"]
                tool_name = tool_call.get("name")
                tool_args = tool_call.get("arguments", {})

                log_step(f"Executing Tool: {tool_name}", payload=tool_args)

                await event_bus.publish(
                    "tool_call",
                    "AgentLoop4",
                    {
                        "step_id": step_id,
                        "session_id": session_id,
                        "tool_name": tool_name,
                        "args_summary": str(tool_args)[:200],
                    },
                )

                try:
                    # Execute tool via ServiceRegistry (returns raw Python object)
                    ctx = ToolContext(
                        user_id=context.plan_graph.graph.get("session_id", "unknown"),
                        metadata={"step_id": step_id},
                    )
                    tool_result = await self.service_registry.route_tool_call(tool_name, tool_args, ctx)

                    # Serialize result to string for agent consumption
                    result_str = str(tool_result)

                    iterations_data[-1]["tool_result"] = result_str
                    log_step("Tool Result", payload={"result_preview": result_str[:200] + "..."})

                    instruction = output.get("thought", "Use the tool result to generate the final output.")
                    if turn == max_turns - 1:
                        instruction += (
                            " \n\nWARNING: This is your FINAL turn. You MUST provide "
                            "the final 'output' now. Do not call any more tools. "
                            "Summarize what you have."
                        )

                    current_input = build_agent_input(
                        instruction=instruction,
                        previous_output=output,
                        iteration_context={"tool_result": result_str},
                    )
                    continue

                except (ToolNotFoundError, ToolExecutionError) as e:
                    log_error(f"Tool Execution Failed: {e}")
                    current_input = build_agent_input(
                        instruction="The tool execution failed. Try a different approach or tool.",
                        previous_output=output,
                        iteration_context={"tool_result": f"Error: {e!s}"},
                    )
                    continue

                except Exception as e:
                    log_error(f"Tool Execution Failed: {e}")
                    current_input = build_agent_input(
                        instruction="The tool execution failed. Try a different approach or tool.",
                        previous_output=output,
                        iteration_context={"tool_result": f"Error: {e!s}"},
                    )
                    continue

            # 2. Check for call_self (legacy recursion)
            elif output.get("call_self"):
                if context._has_executable_code(output):
                    execution_result = await context._auto_execute_code(step_id, output)
                    iterations_data[-1]["execution_result"] = execution_result

                    if execution_result.get("status") == "success":
                        execution_data = execution_result.get("result", {})
                        inputs = {**inputs, **execution_data}

                current_input = build_agent_input(
                    instruction=output.get("next_instruction", "Continue the task"),
                    previous_output=output,
                    iteration_context=output.get("iteration_context", {}),
                )
                continue

            # 3. Final output (no tool call)
            else:
                if context.stop_requested:
                    return {"success": False, "error": "Stop requested"}

                if context._has_executable_code(output):
                    execution_result = await context._auto_execute_code(step_id, output)
                    iterations_data[-1]["execution_result"] = execution_result
                return result

        # Max turns reached
        log_error(f"Max iterations ({max_turns}) reached for {step_id}. Returning last output (incomplete).")
        last_output = iterations_data[-1]["output"] if iterations_data else {"error": "No output produced"}
        return {"success": True, "output": last_output}

    async def _handle_failures(self, context: ExecutionContextManager) -> None:
        """Handle failures via mid-session replanning."""
        log_error("Mid-session replanning not yet implemented")
