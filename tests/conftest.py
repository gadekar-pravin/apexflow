"""Shared pytest fixtures for ApexFlow tests."""

import pytest


@pytest.fixture
def test_user_id() -> str:
    return "test-user-001"
