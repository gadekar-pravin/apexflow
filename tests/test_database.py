"""Tests for core/database.py — connection string building and pool lifecycle."""

from __future__ import annotations

import os
from unittest.mock import patch

from core.database import DatabaseConfig


def test_connection_string_from_database_url() -> None:
    """DATABASE_URL takes highest priority."""
    with patch.dict(os.environ, {"DATABASE_URL": "postgresql://u:p@host/db"}):
        assert DatabaseConfig.get_connection_string() == "postgresql://u:p@host/db"


def test_connection_string_cloud_run() -> None:
    """K_SERVICE triggers Cloud Run path."""
    env = {
        "K_SERVICE": "apexflow-api",
        "ALLOYDB_HOST": "10.0.0.1",
        "ALLOYDB_DB": "apexflow",
        "ALLOYDB_USER": "apexflow",
        "ALLOYDB_PASSWORD": "secret",
    }
    with patch.dict(os.environ, env, clear=False):
        url = DatabaseConfig.get_connection_string()
        assert url == "postgresql://apexflow:secret@10.0.0.1/apexflow"


def test_connection_string_local_defaults() -> None:
    """Local dev uses env vars with localhost fallback."""
    clean_env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("DATABASE_URL", "K_SERVICE", "DB_HOST", "DB_USER", "DB_PASSWORD", "DB_PORT", "DB_NAME")
    }
    with patch.dict(os.environ, clean_env, clear=True):
        url = DatabaseConfig.get_connection_string()
        assert "localhost" in url
        assert "apexflow" in url


def test_connection_string_custom_host() -> None:
    """DB_HOST overrides localhost."""
    env = {"DB_HOST": "10.128.0.5"}
    clean = {k: v for k, v in os.environ.items() if k not in ("DATABASE_URL", "K_SERVICE")}
    clean.update(env)
    with patch.dict(os.environ, clean, clear=True):
        url = DatabaseConfig.get_connection_string()
        assert "10.128.0.5" in url
