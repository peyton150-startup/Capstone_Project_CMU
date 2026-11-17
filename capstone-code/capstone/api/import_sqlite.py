"""One-time, offline-first migration of the existing SQLite simulator journal.

Usage:
  python -m capstone.api.import_sqlite --sqlite /path/to/runs.sqlite
  CAPSTONE_UI_RUN_DATABASE_URL=<secret> python -m capstone.api.import_sqlite \\
      --sqlite /path/to/runs.sqlite --apply --confirm-project-ref PROJECT_REF

The preview does not open the target database. Apply is an atomic, insert-only
copy into an EMPTY migrated Supabase journal. No data is deleted from SQLite.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import uuid
from pathlib import Path
from urllib.parse import quote

MAX_ARTIFACT_BYTES = 8 * 1024 * 1024


def read_source(source: Path):
    """Read a consistent local snapshot without writing to the source file."""
    if not source.is_file():
        raise ValueError("SQLite journal not found")
    uri = "file:" + quote(str(source.resolve())) + "?mode=ro"
    db = sqlite3.connect(uri, uri=True, timeout=5)
    try:
        db.execute("PRAGMA query_only=ON")
        integrity = db.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or integrity[0] != "ok":
            raise ValueError("SQLite journal failed integrity check")
        db.execute("BEGIN")
        runs = db.execute(
            "SELECT run_id, request_key, requested, state, snapshot, "
            "created_at, updated_at FROM runs ORDER BY created_at, run_id"
        ).fetchall()
        events = db.execute(
            "SELECT run_id, seq, event, payload, created_at "
            "FROM run_events ORDER BY run_id, seq"
        ).fetchall()
        reviews = db.execute(
            "SELECT run_id, proposal_id, status, details "
            "FROM run_reviews ORDER BY run_id, proposal_id"
        ).fetchall()
        for row in runs:
            json.loads(row[2])
            json.loads(row[4])
        for row in events:
            json.loads(row[3])
        for row in reviews:
            json.loads(row[3])
        ids = {r[0] for r in runs}
        if any(r[0] not in ids for r in events + reviews):
            raise ValueError("SQLite journal contains orphan event/review rows")
        return runs, events, reviews
    finally:
        db.close()


def artifacts(source: Path, runs):
    """Copy only the simulator's private per-run files, never pilot captures."""
    records = []
    missing = 0
    base = source.parent / "simulator-investigations"
    for row in runs:
        run_id = row[0]
        try:
            if str(uuid.UUID(run_id)) != run_id:
                raise ValueError("Noncanonical run ID")
        except (ValueError, TypeError):
            missing += 1
            continue
        for kind, suffix in (
            ("audit", ".jsonl"),
            ("observability", ".events.jsonl"),
        ):
            path = base / (run_id + suffix)
            if not path.is_file():
                missing += 1
                continue
            with path.open("rb") as handle:
                content = handle.read(MAX_ARTIFACT_BYTES + 1)
            if not content or len(content) > MAX_ARTIFACT_BYTES:
                raise ValueError("Existing simulator artifact exceeds safe import limit")
            records.append((run_id, kind, content, hashlib.sha256(content).hexdigest()))
    return records, missing


def preview(source: Path) -> dict:
    runs, events, reviews = read_source(source)
    stored, missing = artifacts(source, runs)
    return {
        "runs": len(runs),
        "events": len(events),
        "reviews": len(reviews),
        "artifacts": len(stored),
        "missing_artifacts": missing,
        "will_interrupt_incomplete_runs": sum(
            r[3] in ("queued", "running", "awaiting_review") for r in runs
        ),
        "source_unchanged": True,
    }


def apply(source: Path, url: str, project_ref: str) -> dict:
    """Atomic target import, with an explicit project identity guard."""
    from sqlalchemy.engine import make_url

    target = make_url(url)
    ref = project_ref.strip()
    if not ref or not ref.isalnum():
        raise ValueError("A Supabase project ref is required")
    host = target.host or ""
    user = target.username or ""
    if host != f"db.{ref}.supabase.co" and user != f"postgres.{ref}":
        raise ValueError("Database URL does not match the confirmed Supabase project")
    runs, events, reviews = read_source(source)
    saved, missing = artifacts(source, runs)

    from capstone.api.postgres_runs import PostgresSimulatorRuns

    journal = PostgresSimulatorRuns(url, source.parent)
    try:
        with journal._db() as db:
            if db.execute("SELECT 1 FROM runs LIMIT 1").fetchone():
                raise RuntimeError("Target journal must be empty before import")
            for r in runs:
                state = (
                    "interrupted"
                    if r[3] in ("queued", "running", "awaiting_review")
                    else r[3]
                )
                db.execute(
                    "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (r[0], r[1], r[2], state, r[4], r[5], r[6]),
                )
            for e in events:
                db.execute(
                    "INSERT INTO run_events VALUES (?, ?, ?, ?, ?)", e
                )
            for r in reviews:
                status = "expired" if r[2] == "pending" else r[2]
                db.execute(
                    "INSERT INTO run_reviews VALUES (?, ?, ?, ?)",
                    (r[0], r[1], status, r[3]),
                )
            for r in saved:
                db.execute(
                    "INSERT INTO run_artifacts "
                    "(run_id, artifact_type, content, sha256) "
                    "VALUES (?, ?, ?, ?)",
                    r,
                )
        return {
            "runs": len(runs),
            "events": len(events),
            "reviews": len(reviews),
            "artifacts": len(saved),
            "missing_artifacts": missing,
            "destination_updated": True,
            "source_unchanged": True,
        }
    finally:
        journal.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-project-ref")
    args = parser.parse_args()
    if not args.apply:
        result = preview(args.sqlite)
    else:
        if not args.confirm_project_ref:
            parser.error("--apply requires --confirm-project-ref")
        url = os.getenv("CAPSTONE_UI_RUN_DATABASE_URL") or os.getenv("DATABASE_URL")
        if not url:
            parser.error("Set CAPSTONE_UI_RUN_DATABASE_URL or DATABASE_URL privately")
        result = apply(args.sqlite, url, args.confirm_project_ref)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
