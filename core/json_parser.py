from __future__ import annotations

import json
import re
from typing import Any

from json_repair import repair_json


class JsonParsingError(Exception):
    pass


def extract_json_block_fenced(text: str) -> str | None:
    """Extracts the content of a ```json fenced code block."""
    match = re.search(r"(?i)```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    return match.group(1) if match else None


def extract_json_block_balanced(text: str) -> str | None:
    """Finds the largest balanced JSON-looking block from first '{' to last '}'."""
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return text[start : end + 1]
    return None


def validate_required_keys(obj: dict[str, Any], required_keys: list[str]) -> None:
    """Ensures all required keys exist in the parsed dictionary."""
    for key in required_keys:
        if key not in obj:
            raise JsonParsingError(f"Missing required key: {key}")


def _parse_and_validate(raw_json: str, required_keys: list[str] | None = None) -> dict[str, Any]:
    """Helper to parse and optionally validate required schema."""
    parsed: dict[str, Any] = json.loads(raw_json)
    if required_keys:
        validate_required_keys(parsed, required_keys)
    return parsed


def parse_llm_json(text: str, required_keys: list[str] | None = None, debug: bool = False) -> dict[str, Any]:
    """
    Attempts to robustly parse a JSON object from LLM output.
    Tries:
      1. fenced JSON
      2. balanced braces
      3. repaired JSON
    """
    extractors = [("fenced", extract_json_block_fenced), ("balanced", extract_json_block_balanced)]

    for name, extractor in extractors:
        raw_json = extractor(text)
        if raw_json:
            try:
                if debug:
                    print(f"[DEBUG] Attempting {name} extraction...")
                return _parse_and_validate(raw_json, required_keys)
            except json.JSONDecodeError:
                if debug:
                    print(f"[DEBUG] JSON decode failed for {name}.")
                continue
            except JsonParsingError:
                raise  # Required key missing

    # Final attempt: repair
    raw_json = extract_json_block_balanced(text)
    if raw_json:
        try:
            if debug:
                print("[DEBUG] Attempting auto-repair...")
            repaired = repair_json(raw_json)
            if isinstance(repaired, dict | list):
                if required_keys and isinstance(repaired, dict):
                    validate_required_keys(repaired, required_keys)
                return dict(repaired) if isinstance(repaired, dict) else {"items": repaired}
            return _parse_and_validate(str(repaired), required_keys)
        except Exception:
            if debug:
                print("[DEBUG] Repair attempt failed.")

    raise JsonParsingError("All attempts to parse JSON from LLM output failed.")
