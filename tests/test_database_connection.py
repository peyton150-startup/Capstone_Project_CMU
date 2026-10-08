"""Offline checks; the live Neon probe is run separately."""

import pytest

pytest.importorskip("sqlalchemy")

from capstone.database.connection import check_database_connection


def test_select_one_returns_true(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    assert check_database_connection() is True


def test_empty_url_fails_before_connecting(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    with pytest.raises(ValueError, match="DATABASE_URL"):
        check_database_connection()
