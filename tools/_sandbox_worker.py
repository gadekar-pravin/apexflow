"""Subprocess worker for Monty sandbox execution.

Spawned by tools/monty_sandbox.py. Communicates via JSON-lines over stdin/stdout.

IPC Protocol (JSON-lines over stdin/stdout):
  Parent -> Worker: init config (code, inputs, external_names, limits)
  Worker -> Parent: call request (name, args)
  Parent -> Worker: result or call_error
  Worker -> Parent: done (output) or error (message, type)
"""

from __future__ import annotations

import json
import platform
import sys


def _set_memory_limit(max_memory_mb: int) -> None:
    """Best-effort memory limit via setrlimit (Linux only)."""
    if platform.system() != "Linux":
        return
    try:
        import resource

        limit_bytes = max_memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))
    except (ValueError, OSError):
        pass


def _send(msg: dict[str, object]) -> None:
    """Write a JSON line to stdout."""
    sys.stdout.write(json.dumps(msg, default=str) + "\n")
    sys.stdout.flush()


def _recv() -> dict[str, object]:
    """Read a JSON line from stdin."""
    line = sys.stdin.readline()
    if not line:
        raise EOFError("Parent closed stdin")
    return json.loads(line)  # type: ignore[no-any-return]


def main() -> None:
    try:
        init_msg = _recv()
        if init_msg.get("type") != "init":
            _send({"type": "error", "error": "Expected init message", "error_type": "ProtocolError"})
            return

        code = str(init_msg.get("code", ""))
        raw_inputs = init_msg.get("inputs")
        inputs: dict[str, object] = dict(raw_inputs) if isinstance(raw_inputs, dict) else {}
        raw_ext = init_msg.get("external_names")
        external_names: list[str] = list(raw_ext) if isinstance(raw_ext, list) else []
        raw_calls = init_msg.get("max_external_calls")
        if isinstance(raw_calls, int | float):
            max_external_calls = int(raw_calls)
        elif isinstance(raw_calls, str):
            try:
                max_external_calls = int(raw_calls)
            except ValueError:
                max_external_calls = 100_000
        else:
            max_external_calls = 100_000
        raw_mem = init_msg.get("max_memory_mb")
        if isinstance(raw_mem, int | float):
            max_memory_mb = int(raw_mem)
        elif isinstance(raw_mem, str):
            try:
                max_memory_mb = int(raw_mem)
            except ValueError:
                max_memory_mb = 256
        else:
            max_memory_mb = 256

        _set_memory_limit(max_memory_mb)

        import pydantic_monty

        monty = pydantic_monty.Monty(
            code,
            inputs=list(inputs.keys()) if inputs else [],
            external_functions=external_names,
        )

        result = monty.start(inputs=inputs) if inputs else monty.start()
        external_calls = 0

        while isinstance(result, pydantic_monty.MontySnapshot):
            if external_calls >= max_external_calls:
                _send(
                    {
                        "type": "error",
                        "error": f"External call limit exceeded ({max_external_calls})",
                        "error_type": "ExternalCallLimitExceeded",
                    }
                )
                return

            _send(
                {
                    "type": "call",
                    "name": result.function_name,
                    "args": list(result.args) if result.args else [],
                }
            )

            response = _recv()
            resp_type = response.get("type")

            if resp_type == "result":
                result = result.resume(return_value=response.get("value"))
            elif resp_type == "call_error":
                result = result.resume(return_value=f"ERROR: {response.get('error', 'Unknown error')}")
            else:
                err = f"Unexpected message type: {resp_type}"
                _send({"type": "error", "error": err, "error_type": "ProtocolError"})
                return

            external_calls += 1

        # MontyComplete
        _send({"type": "done", "output": result.output})

    except Exception as exc:
        _send({"type": "error", "error": str(exc), "error_type": type(exc).__name__})


if __name__ == "__main__":
    main()
