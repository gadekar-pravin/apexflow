# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ApexFlow v2 is a web-first rewrite of the desktop-first ApexFlow v1. It's an intelligent workflow automation platform powered by Google Gemini. The backend is FastAPI + asyncpg + AlloyDB (Google's PostgreSQL variant with ScaNN vector indexes).

**Current state:** Phase 1 (bootstrap + database) is complete. Phases 2-5 are documented in `docs/` but not yet implemented. Most directories (`agents/`, `services/`, `routers/`, etc.) contain only `__init__.py` files.

## Common Commands

```bash
# Install dependencies (use venv at .venv/)
pip install -e ".[dev]"

# Run tests
pytest tests/ -v
pytest tests/test_database.py -v              # single file
pytest tests/test_database.py::test_name -v   # single test

# Lint and format
ruff check .          # lint
ruff check . --fix    # lint with auto-fix
ruff format .         # format

# Type check
mypy core/

# Pre-commit (runs ruff + mypy + whitespace fixes)
pre-commit run --all-files

# Database migrations
alembic upgrade head        # apply all migrations
alembic stamp 001           # mark migration as applied (if schema already exists)
alembic revision -m "desc"  # create new migration

# Dev environment (GCE VM with AlloyDB Omni)
./scripts/dev-start.sh      # start VM + SSH tunnel to localhost:5432
./scripts/dev-stop.sh       # close tunnel + stop VM
```

## Architecture

### Database

AlloyDB Omni 15.12.0 runs on a GCE VM (`alloydb-omni-dev`, `n2-standard-4`, `us-central1-a`). Developers connect via SSH tunnel (`localhost:5432`). The schema has 13 tables defined in `scripts/init-db.sql`.

**Connection priority** (`core/database.py`):
1. `DATABASE_URL` env var (explicit override)
2. `K_SERVICE` detected → Cloud Run mode using `ALLOYDB_*` vars
3. Local dev → builds from `DB_HOST`/`DB_USER`/`DB_PASSWORD`/`DB_PORT`/`DB_NAME` (defaults to `localhost:5432`, user `apexflow`)

**Connection pool:** asyncpg, min_size=1, max_size=5 (configurable via `DB_POOL_MAX`).

**Alembic** uses psycopg2 (sync driver), not asyncpg. The env.py mirrors the same 3-priority connection logic with a `postgresql+psycopg2://` prefix.

**ScaNN indexes** cannot be created on empty tables in AlloyDB. They are deferred until data insertion. Use `scripts/create-scann-indexes.sql` after populating `memories` and `document_chunks`. CI uses pgvector with IVFFlat as fallback.

### CI Pipeline

Google Cloud Build (`cloudbuild.yaml`), not GitHub Actions. Trigger fires on PRs to `main` only, with path filters (skips docs, scripts, config-only changes).

Steps: start pgvector container → wait for DB → lint (ruff) + typecheck (mypy) in parallel → migrate (alembic) → test (pytest). All steps share the `cloudbuild` Docker network; the DB container is reachable by hostname `postgres`.

### Project Layout

- `core/` — Database pool, skills framework, stores (data access), RAG engine
- `agents/` — Agent implementations (Planner, Router, etc.)
- `memory/` — Session memory and REMME indexing
- `remme/` — Memory management system (hubs, engines, sources)
- `services/` — Business logic layer
- `routers/` — FastAPI route handlers
- `tools/` — Agent tools and code sandbox
- `config/` — Settings and configuration
- `prompts/` — Prompt templates
- `docs/` — Phase documentation (7 phase docs + rewrite plan)

## Code Conventions

- **Python 3.12+**, strict mypy with pydantic plugin
- **Ruff rules:** E, F, I, UP, B, SIM at 120-char line length
- **Primary keys:** TEXT type, generated in application layer
- **Async:** asyncpg for all DB access in application code; psycopg2 only for Alembic migrations
- **Schema:** CHECK constraints for status/role enums, JSONB for schemaless fields, NUMERIC(10,6) for monetary values

## GCP Configuration

- **Project:** `apexflow-ai`
- **VM:** `alloydb-omni-dev` in `us-central1-a`
- **Cloud Scheduler:** `vm-auto-stop` stops the VM nightly at 10 PM ET
- **Cloud Build SA:** `cloudbuild-ci@apexflow-ai.iam.gserviceaccount.com`
