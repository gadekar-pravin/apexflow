"""Tests for core/json_parser.py — robust LLM JSON extraction and repair."""

from __future__ import annotations

import pytest

from core.json_parser import (
    JsonParsingError,
    extract_json_block_balanced,
    extract_json_block_fenced,
    parse_llm_json,
    validate_required_keys,
)

# ---------------------------------------------------------------------------
# extract_json_block_fenced
# ---------------------------------------------------------------------------


def test_fenced_extraction_basic() -> None:
    text = '```json\n{"key": "value"}\n```'
    result = extract_json_block_fenced(text)
    assert result is not None
    assert '"key"' in result


def test_fenced_extraction_with_surrounding_text() -> None:
    text = 'Here is the result:\n```json\n{"a": 1}\n```\nDone.'
    result = extract_json_block_fenced(text)
    assert result is not None
    assert '"a"' in result


def test_fenced_extraction_no_fence() -> None:
    text = '{"key": "value"}'
    result = extract_json_block_fenced(text)
    assert result is None


def test_fenced_extraction_case_insensitive() -> None:
    text = '```JSON\n{"x": 1}\n```'
    result = extract_json_block_fenced(text)
    assert result is not None


# ---------------------------------------------------------------------------
# extract_json_block_balanced
# ---------------------------------------------------------------------------


def test_balanced_extraction_basic() -> None:
    text = 'prefix {"key": "value"} suffix'
    result = extract_json_block_balanced(text)
    assert result == '{"key": "value"}'


def test_balanced_extraction_nested() -> None:
    text = 'Some text {"outer": {"inner": 42}} end'
    result = extract_json_block_balanced(text)
    assert result is not None
    assert "inner" in result


def test_balanced_extraction_no_braces() -> None:
    text = "no json here"
    result = extract_json_block_balanced(text)
    assert result is None


def test_balanced_extraction_only_open_brace() -> None:
    text = "start { but no close"
    result = extract_json_block_balanced(text)
    assert result is None


# ---------------------------------------------------------------------------
# validate_required_keys
# ---------------------------------------------------------------------------


def test_validate_required_keys_all_present() -> None:
    obj = {"a": 1, "b": 2, "c": 3}
    # Should not raise
    validate_required_keys(obj, ["a", "b"])


def test_validate_required_keys_missing() -> None:
    obj = {"a": 1}
    with pytest.raises(JsonParsingError, match="Missing required key: b"):
        validate_required_keys(obj, ["a", "b"])


# ---------------------------------------------------------------------------
# parse_llm_json — clean JSON
# ---------------------------------------------------------------------------


def test_parse_clean_json_fenced() -> None:
    text = '```json\n{"action": "search", "query": "python"}\n```'
    result = parse_llm_json(text)
    assert result["action"] == "search"
    assert result["query"] == "python"


def test_parse_clean_json_bare() -> None:
    text = '{"action": "run", "count": 5}'
    result = parse_llm_json(text)
    assert result["action"] == "run"
    assert result["count"] == 5


def test_parse_clean_json_with_required_keys() -> None:
    text = '{"action": "go", "target": "home"}'
    result = parse_llm_json(text, required_keys=["action", "target"])
    assert result["action"] == "go"


def test_parse_clean_json_missing_required_key() -> None:
    text = '{"action": "go"}'
    with pytest.raises(JsonParsingError, match="Missing required key"):
        parse_llm_json(text, required_keys=["action", "target"])


# ---------------------------------------------------------------------------
# parse_llm_json — with surrounding LLM text
# ---------------------------------------------------------------------------


def test_parse_json_surrounded_by_text() -> None:
    text = 'Sure! Here is the plan:\n```json\n{"step": 1, "task": "analyze"}\n```\nLet me know if you need more.'
    result = parse_llm_json(text)
    assert result["step"] == 1


def test_parse_json_no_fence_with_prose() -> None:
    text = 'I think the answer is {"result": "yes", "confidence": 0.95} based on analysis.'
    result = parse_llm_json(text)
    assert result["result"] == "yes"


# ---------------------------------------------------------------------------
# parse_llm_json — repair mode
# ---------------------------------------------------------------------------


def test_parse_repaired_json_trailing_comma() -> None:
    """json_repair should handle trailing commas."""
    text = '{"a": 1, "b": 2,}'
    result = parse_llm_json(text)
    assert result["a"] == 1
    assert result["b"] == 2


def test_parse_repaired_json_single_quotes() -> None:
    """json_repair should handle single-quoted keys/values."""
    text = "{'key': 'value'}"
    result = parse_llm_json(text)
    assert result["key"] == "value"


# ---------------------------------------------------------------------------
# parse_llm_json — total failure
# ---------------------------------------------------------------------------


def test_parse_totally_invalid_raises() -> None:
    text = "This is just plain text with no JSON at all."
    with pytest.raises(JsonParsingError, match="All attempts"):
        parse_llm_json(text)
