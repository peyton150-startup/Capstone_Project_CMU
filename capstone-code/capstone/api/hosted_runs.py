"""FastAPI-only facade over the shared PostgreSQL queue (no agent imports).

The current hosted deployment is single-tenant, identified by server-owned
role credentials. Actor identity is never taken from a request parameter.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from capstone.api.readers import safe_investigation_detail
from capstone.api.run_repository import RunExecutionConfig, RunRepository
from capstone.api.runs import ReviewDecision, RunRequest

_HOSTED_ACTOR = "hosted-simulator"


class HostedSimulatorRuns:
    """Preserve the managed-run HTTP contract while never executing a model."""

    def __init__(self, database_url: str):
        self.repository = RunRepository(database_url)
        if not self.repository.ready():
            self.repository.close()
            raise RuntimeError("Hosted run schema not migrated")

    def ready(self) -> bool:
        return self.repository.ready()

    def queue_metrics(self) -> dict[str, Any]:
        """Return bounded operational counts, never worker secrets/lease tokens."""
        return self.repository.queue_metrics()

    def close(self) -> None:
        self.repository.close()

    def submit(self, request: RunRequest, key: str) -> dict[str, Any]:
        from capstone.settings import get_settings

        settings = get_settings()
        revision = os.getenv("CAPSTONE_SOURCE_REVISION") or None
        effective = RunExecutionConfig(
            triage_plan=settings.triage_plan,
            triage_investigate=settings.triage_investigate,
            triage_hypothesize=settings.triage_hypothesize,
            triage_evidence_tests=settings.triage_evidence_tests,
            source_revision=revision,
        )
        return self.repository.submit(
            request, key, actor_id=_HOSTED_ACTOR, effective_config=effective
        )

    def get(self, run_id: str) -> dict[str, Any] | None:
        return self.repository.get(run_id, actor_id=_HOSTED_ACTOR)

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.repository.list_runs(actor_id=_HOSTED_ACTOR, limit=limit)

    def events_since(
        self, run_id: str, cursor: int, limit: int = 100
    ) -> list[dict[str, Any]]:
        return self.repository.events_since(
            run_id, cursor, actor_id=_HOSTED_ACTOR, limit=limit
        )

    def pending_reviews(self) -> list[dict[str, Any]]:
        return self.repository.pending_reviews(actor_id=_HOSTED_ACTOR)

    def decide(self, run_id: str, decision: ReviewDecision) -> dict[str, Any]:
        return self.repository.decide_review(
            run_id, decision, actor_id=_HOSTED_ACTOR, reviewer_id="hosted-reviewer"
        )

    def investigation_detail(
        self, run_id: str, investigation_id: str
    ) -> dict[str, Any] | None:
        """Project a private audit into its pre-existing strictly safe reader."""
        content = self.repository.read_artifact(
            run_id, "audit", actor_id=_HOSTED_ACTOR
        )
        if content is None:
            return None
        with tempfile.TemporaryDirectory(prefix="capstone-projection-") as root:
            path = Path(root) / "audit.jsonl"
            path.write_bytes(content)
            return safe_investigation_detail(path, investigation_id)

    def observability_items(self, run_id: str) -> list[dict[str, Any]] | None:
        """Return only the already-approved operational counters from stored logs."""
        content = self.repository.read_artifact(
            run_id, "observability", actor_id=_HOSTED_ACTOR
        )
        if content is None:
            return None
        items = []
        for line in content.decode("utf-8", errors="replace").splitlines()[-500:]:
            try:
                row = json.loads(line)
            except (ValueError, TypeError):
                continue
            if not isinstance(row, dict):
                continue
            event = row.get("event")
            if not isinstance(event, str) or not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", event
            ):
                continue
            safe: dict[str, Any] = {"event": event}
            for key in ("run_id", "investigation_id", "tool"):
                value = row.get(key)
                if isinstance(value, str) and re.fullmatch(
                    r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", value
                ):
                    safe[key] = value
            tick = row.get("tick")
            if type(tick) is int and 0 <= tick <= 1_000_000_000:
                safe["tick"] = tick
            if type(row.get("success")) is bool:
                safe["success"] = row["success"]
            counts = row.get("counts")
            if isinstance(counts, dict):
                safe["counts"] = {
                    name: count
                    for name, count in counts.items()
                    if isinstance(name, str)
                    and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", name)
                    and type(count) is int
                    and 0 <= count <= 1_000_000
                }
            items.append(safe)
        return items
