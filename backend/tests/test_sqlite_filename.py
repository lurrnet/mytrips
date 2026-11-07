"""Check safe DB rename and prevention of silently creating an empty database."""
import sqlite3
from pathlib import Path

import pytest

from backend.database import _ensure_legacy_db_is_not_silently_ignored
from scripts.rename_sqlite_db import migrate_sqlite_database


def test_copy_includes_wal_and_preserves_source(tmp_path: Path):
    old = tmp_path / "partiu.db"
    with sqlite3.connect(old) as src:
        src.execute("PRAGMA journal_mode=WAL")
        src.execute("CREATE TABLE bookings (reference TEXT NOT NULL)")
        src.execute("INSERT INTO bookings VALUES ('booking-123')")
        src.commit()
        assert migrate_sqlite_database(tmp_path)
        with sqlite3.connect(tmp_path / "mytrips.db") as dest:
            assert dest.execute("SELECT reference FROM bookings").fetchone()[0] == "booking-123"
            assert dest.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert old.exists()


def test_does_not_overwrite(tmp_path: Path):
    with sqlite3.connect(tmp_path / "partiu.db") as db:
        db.execute("CREATE TABLE old_table (id INTEGER)")
    with sqlite3.connect(tmp_path / "mytrips.db") as db:
        db.execute("CREATE TABLE new_table (id INTEGER)")
    with pytest.raises(FileExistsError, match="Both"):
        migrate_sqlite_database(tmp_path)
    with sqlite3.connect(tmp_path / "mytrips.db") as db:
        assert db.execute(
            "SELECT name FROM sqlite_master WHERE name='new_table'"
        ).fetchone() is not None


def test_fresh_install_noop(tmp_path: Path):
    assert not migrate_sqlite_database(tmp_path)


def test_guard_prevents_empty_database(tmp_path: Path, monkeypatch):
    from backend.config import settings
    with sqlite3.connect(tmp_path / "partiu.db") as db:
        db.execute("CREATE TABLE bookings (id INTEGER)")
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "mytrips.db"))
    with pytest.raises(RuntimeError, match="rename_sqlite_db.py"):
        _ensure_legacy_db_is_not_silently_ignored()
    assert not (tmp_path / "mytrips.db").exists()


def test_guard_allows_fresh_install(tmp_path: Path, monkeypatch):
    from backend.config import settings
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "mytrips.db"))
    _ensure_legacy_db_is_not_silently_ignored()
