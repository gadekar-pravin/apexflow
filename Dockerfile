# ---- Builder stage ----
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock* ./

# Install production dependencies only (without the project itself)
RUN uv venv /app/.venv && uv sync --no-dev --frozen --no-install-project

# Copy application code
COPY . .

# Install the project now that sources are available
RUN uv sync --no-dev --frozen

# ---- Runtime stage ----
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Create non-root user
RUN groupadd --gid 1001 appuser && \
    useradd --uid 1001 --gid appuser --create-home appuser

WORKDIR /app

# Copy venv and application code from builder
COPY --from=builder /app /app

# Put venv on PATH
ENV PATH="/app/.venv/bin:$PATH"

# Switch to non-root user
USER appuser

EXPOSE 8080

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
