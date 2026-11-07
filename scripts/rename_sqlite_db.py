#!/usr/bin/env python3
"""Safely copy a stopped legacy Partiu SQLite database to mytrips.db.

Uses SQLite backup API so committed transactions in partiu.db-wal are included.
Stop all writers first. Never deletes the original or overwrites the new DB.
"""
import argparse
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from urllib.parse import quote


def migrate_sqlite_database(data_dir: Path) -> bool:
    data_dir = data_dir.resolve()
    old = data_dir / "partiu.db"
    new = data_dir / "mytrips.db"
    if new.exists():
        if old.exists():
            raise FileExistsError(f"Both {old} and {new} exist; resolve manually.")
        print(f"Already migrated: {new}")
        return False
    if not old.exists():
        print(f"No legacy database at {old}; fresh install can initialize {new}.")
        return False
    if old.is_symlink() or not old.is_file():
        raise ValueError(f"Not a regular SQLite file: {old}")

    previous_umask = os.umask(0o077)
    try:
        fd, name = tempfile.mkstemp(dir=data_dir, prefix=".mytrips-copy-", suffix=".db")
    finally:
        os.umask(previous_umask)
    os.close(fd)
    tmp = Path(name)
    try:
        uri = f"file:{quote(str(old), safe='/')}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as src:
            if src.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError(f"Integrity check failed: {old}")
            with closing(sqlite3.connect(tmp)) as dst:
                src.backup(dst)
                if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Copied database failed integrity check")
        os.chmod(tmp, 0o600)
        os.link(tmp, new)  # atomic and fails if new exists; no overwriting.
    finally:
        tmp.unlink(missing_ok=True)
    print(f"Copied database to {new}; left {old} unchanged.")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).resolve().parent.parent / "data")
    args = parser.parse_args()
    migrate_sqlite_database(args.data_dir)
