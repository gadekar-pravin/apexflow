"""Document chunking for RAG (Retrieval Augmented Generation).

Two strategies:

1) Rule-Based (Recursive):
   - Fast, dependency-free.
   - Hierarchically splits by: paragraphs -> lines -> sentences -> words -> characters.
   - Applies inter-chunk overlap at every boundary for retrieval continuity.

2) Semantic (Rohan V2, Gemini):
   - Optional, LLM-driven.
   - Processes text in word blocks and asks the LLM for a topic-shift boundary.
   - Splits at the returned word index; carries remainder forward to preserve flow.
   - Post-processes any oversized semantic chunks using rule-based splitting to
     guarantee max chunk length.

Notes:
- `chunk_size` is a target maximum in characters. Overlap is applied after the
  initial split, so final chunk length can be up to `chunk_size + chunk_overlap`.
  If you need a strict max-length, enforce it downstream or trim overlap.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults — loaded from settings config, with hardcoded fallbacks
# ---------------------------------------------------------------------------

_DEFAULT_CHUNK_SIZE = 2000  # characters
_DEFAULT_CHUNK_OVERLAP = 200  # characters
_DEFAULT_SEMANTIC_BLOCK_WORDS = 1024
_DEFAULT_SEMANTIC_MODEL = "gemini-2.5-flash-lite"

# Approximate conversion used by the original code.
_CHARS_PER_TOKEN = 4

try:
    from config.settings_loader import load_settings

    _settings = load_settings() or {}

    _rag_cfg = _settings.get("rag", {})
    # Settings values are in tokens; 1 token ≈ 4 chars.
    _max_chunk_tokens = int(_rag_cfg.get("max_chunk_length", 512))
    _overlap_tokens = int(_rag_cfg.get("chunk_overlap", 40))

    DEFAULT_CHUNK_SIZE: int = _max_chunk_tokens * _CHARS_PER_TOKEN  # tokens → chars
    DEFAULT_CHUNK_OVERLAP: int = _overlap_tokens * _CHARS_PER_TOKEN

    SEMANTIC_BLOCK_WORDS: int = int(_rag_cfg.get("semantic_word_limit", _DEFAULT_SEMANTIC_BLOCK_WORDS))

    _models_cfg = _settings.get("models", {})
    SEMANTIC_MODEL: str = str(_models_cfg.get("semantic_chunking", _DEFAULT_SEMANTIC_MODEL))

except Exception:
    DEFAULT_CHUNK_SIZE = _DEFAULT_CHUNK_SIZE
    DEFAULT_CHUNK_OVERLAP = _DEFAULT_CHUNK_OVERLAP
    SEMANTIC_BLOCK_WORDS = _DEFAULT_SEMANTIC_BLOCK_WORDS
    SEMANTIC_MODEL = _DEFAULT_SEMANTIC_MODEL


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def chunk_document(
    text: str,
    method: str = "rule_based",
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    """Chunk a document into segments for embedding.

    Args:
        text: Full document text.
        method: "rule_based" (default) or "semantic" (LLM-driven).
        chunk_size: Target chunk size in characters.
        chunk_overlap: Overlap in characters carried between adjacent chunks.

    Returns:
        List of text chunks.
    """
    if not text or not text.strip():
        return []

    chunk_size, chunk_overlap = _validate_chunk_params(chunk_size, chunk_overlap)

    if method == "semantic":
        try:
            chunks = await _chunk_semantic_rohan_v2(text)
            # Enforce max length so embedding never sees runaway chunk sizes.
            return _enforce_max_chunk_size(chunks, chunk_size, chunk_overlap)
        except Exception:
            logger.exception("Semantic chunking failed; falling back to rule_based")
            return _chunk_recursive(text, chunk_size, chunk_overlap)

    return _chunk_recursive(text, chunk_size, chunk_overlap)


def _validate_chunk_params(chunk_size: int, chunk_overlap: int) -> tuple[int, int]:
    """Sanitize chunk parameters to avoid pathological behavior."""
    try:
        chunk_size = int(chunk_size)
        chunk_overlap = int(chunk_overlap)
    except Exception as e:
        raise ValueError("chunk_size and chunk_overlap must be integers") from e

    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")

    if chunk_overlap < 0:
        logger.warning("chunk_overlap < 0 (%d); clamping to 0", chunk_overlap)
        chunk_overlap = 0

    if chunk_overlap >= chunk_size:
        # Clamping is safer than raising in most pipeline contexts.
        new_overlap = max(min(chunk_size // 2, chunk_size - 1), 0)
        logger.warning(
            "chunk_overlap (%d) >= chunk_size (%d); clamping overlap to %d",
            chunk_overlap,
            chunk_size,
            new_overlap,
        )
        chunk_overlap = new_overlap

    return chunk_size, chunk_overlap


# ---------------------------------------------------------------------------
# Rule-based recursive splitter
# ---------------------------------------------------------------------------

# Slightly richer than the original; still cheap and dependency-free.
_SEPARATORS: list[str] = ["\n\n", "\n", ". ", ".\n", "? ", "! ", " ", ""]


def _chunk_recursive(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Hierarchical recursive splitting with inter-chunk overlap."""
    raw = _split_text_recursive(text, _SEPARATORS, chunk_size, chunk_overlap)

    # Apply inter-chunk overlap: carry last `chunk_overlap` chars into next chunk
    if chunk_overlap <= 0 or len(raw) <= 1:
        return raw

    overlapped: list[str] = [raw[0]]
    for i in range(1, len(raw)):
        prev = raw[i - 1]
        tail = prev[-chunk_overlap:] if len(prev) > chunk_overlap else prev
        # Only prepend overlap if the next chunk doesn't already start with it
        if tail and not raw[i].startswith(tail):
            overlapped.append(tail + raw[i])
        else:
            overlapped.append(raw[i])

    return overlapped


def _split_text_recursive(
    text: str,
    separators: list[str],
    chunk_size: int,
    chunk_overlap: int,
) -> list[str]:
    """Recursively split text, guaranteeing each emitted chunk <= chunk_size.

    The last separator is "" (hard character split).

    Important: This function preserves separators by attaching each separator to
    the *end* of each split fragment (except the last), so boundaries retain
    fidelity when a chunk break occurs.
    """
    if len(text) <= chunk_size or not separators:
        return [text]

    separator = separators[0]
    next_separators = separators[1:]

    # Hard character split (last resort)
    if separator == "":
        step = max(chunk_size - chunk_overlap, 1)
        return [text[i : i + chunk_size] for i in range(0, len(text), step)]

    if separator not in text:
        return _split_text_recursive(text, next_separators, chunk_size, chunk_overlap)

    splits = text.split(separator)

    # Rebuild parts with separator preserved at the end of each part except the last.
    parts: list[str] = []
    for i, s in enumerate(splits):
        if i < len(splits) - 1:
            parts.append(s + separator)
        else:
            parts.append(s)

    chunks: list[str] = []
    current = ""

    def commit(s: str) -> None:
        # Drop whitespace-only chunks; otherwise preserve as-is.
        if s and s.strip():
            chunks.append(s)

    for part in parts:
        if not part:
            continue

        # If a single part is too large, recurse into smaller separators.
        if len(part) > chunk_size:
            if current:
                commit(current)
                current = ""

            # If we have no more separators, force hard split.
            if not next_separators:
                chunks.extend(_split_text_recursive(part, [""], chunk_size, chunk_overlap))
            else:
                chunks.extend(_split_text_recursive(part, next_separators, chunk_size, chunk_overlap))
            continue

        if not current:
            current = part
            continue

        candidate = current + part
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            commit(current)
            current = part

    if current:
        commit(current)

    # Final safety: ensure no chunk exceeds chunk_size.
    final: list[str] = []
    for c in chunks:
        if len(c) <= chunk_size:
            final.append(c)
        else:
            final.extend(_split_text_recursive(c, next_separators or [""], chunk_size, chunk_overlap))

    return final


def _enforce_max_chunk_size(
    chunks: list[str],
    chunk_size: int,
    chunk_overlap: int,
) -> list[str]:
    """Ensure no chunk exceeds chunk_size by splitting oversized items."""
    out: list[str] = []
    for c in chunks:
        if len(c) <= chunk_size:
            out.append(c)
        else:
            out.extend(_chunk_recursive(c, chunk_size, chunk_overlap))
    return out


# ---------------------------------------------------------------------------
# Semantic chunker — Rohan V2 (Gemini)
# ---------------------------------------------------------------------------


async def _chunk_semantic_rohan_v2(text: str) -> list[str]:
    """Rohan's Semantic Chunking Strategy V2.

    1. Slice input into blocks of ~SEMANTIC_BLOCK_WORDS words.
    2. Ask the LLM for a topic shift word index within the block.
    3. If shift found — split at shift point, carry remainder to next block.
    4. If no shift — commit block, move on.
    """
    from core.gemini_client import get_gemini_client

    client = get_gemini_client()

    words = text.split()
    final_chunks: list[str] = []
    current_index = 0
    buffer_words: list[str] = []

    # Avoid overly tiny splits.
    min_words_before_split = max(30, SEMANTIC_BLOCK_WORDS // 32)

    while current_index < len(words) or buffer_words:
        # Fill buffer to target block size
        needed = SEMANTIC_BLOCK_WORDS - len(buffer_words)
        if needed > 0 and current_index < len(words):
            take = min(needed, len(words) - current_index)
            buffer_words.extend(words[current_index : current_index + take])
            current_index += take

        if not buffer_words:
            break

        # Small trailing block — commit directly
        if current_index >= len(words) and len(buffer_words) < (SEMANTIC_BLOCK_WORDS // 2):
            final_chunks.append(" ".join(buffer_words))
            break

        block_text = " ".join(buffer_words)

        # Detect topic shift via LLM
        try:
            split_word_index = await _detect_topic_shift_word_index(client, block_text)
        except Exception as e:
            logger.warning("LLM topic detection failed: %s. Committing block as-is.", e)
            split_word_index = None

        if split_word_index is not None and split_word_index >= min_words_before_split:
            # Split the buffer at the word index.
            left = buffer_words[:split_word_index]
            right = buffer_words[split_word_index:]

            if left:
                final_chunks.append(" ".join(left))

            buffer_words = right
            logger.info("Semantic split: carried over %d words.", len(buffer_words))

            # If the model keeps returning a too-small index or we get stuck,
            # commit to avoid infinite loops.
            if not buffer_words:
                continue
        else:
            final_chunks.append(block_text)
            buffer_words = []

    return final_chunks


async def _detect_topic_shift_word_index(client: Any, text: str) -> int | None:
    """Query Gemini for a topic boundary within *text*.

    Returns:
        0-based word index where the new topic starts, or None if no shift.

    We ask the model for a strict JSON response, but also implement tolerant
    parsing in case the model returns extra text.
    """

    # Import only when semantic chunking is used.
    from google.genai import types

    prompt = (
        "You are detecting topic boundaries for semantic chunking.\n"
        "Analyze the following text block and decide if there is a clear shift to a new,"
        " unrelated topic or section.\n\n"
        "Return ONLY valid JSON in one of these forms:\n"
        '  {"shift": false}\n'
        '  {"shift": true, "start_word_index": <int>}\n\n'
        "Rules:\n"
        "- Be conservative: only mark shift=true if topics are clearly distinct.\n"
        "- start_word_index is 0-based within this block and must point to the first word"
        "  of the new topic section.\n"
        "- If no shift, use shift=false.\n\n"
        f"Text Block:\n{text}\n"
    )

    response = await client.aio.models.generate_content(
        model=SEMANTIC_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.0,
            max_output_tokens=80,
        ),
    )

    raw = (getattr(response, "text", "") or "").strip()
    if not raw:
        return None

    # Fast-path: handle older NO_SHIFT style outputs.
    if "NO_SHIFT" in raw.upper():
        return None

    data = _parse_shift_json(raw)
    if not data:
        return None

    if not data.get("shift"):
        return None

    idx = data.get("start_word_index")
    if isinstance(idx, bool) or idx is None:
        return None

    try:
        idx_int = int(idx)
    except Exception:
        return None

    # Validate against block length
    n_words = len(text.split())
    if idx_int <= 0 or idx_int >= n_words:
        return None

    return idx_int


def _parse_shift_json(raw: str) -> dict[str, Any] | None:
    """Parse the model response as JSON, with a tolerant fallback."""
    # Try direct JSON
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    # Try extracting a JSON object from surrounding text
    m = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass

    # Regex fallback: shift true/false and integer index
    shift_match = re.search(r"\bshift\b\s*[:=]\s*(true|false)", raw, flags=re.IGNORECASE)
    idx_match = re.search(r"\bstart_word_index\b\s*[:=]\s*(\d+)", raw)

    if shift_match:
        shift_val = shift_match.group(1).lower() == "true"
        idx_val = int(idx_match.group(1)) if idx_match else None
        return {"shift": shift_val, "start_word_index": idx_val}

    return None
