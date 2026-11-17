"""Allowlisted sources for a single-host, read-only UI.

All paths come from the trusted server process environment, never from HTTP.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class UiConfig:
    # Variables:
    #   capture/audit/experiment/investigations: Privately approved local artifacts.
    #   token: Local browser-to-API authentication secret; never sent in responses.
    #   evaluator: Explicit opt-in for evaluator-only score views.
    #   show_values: Explicit opt-in for permitted raw sensor values.
    capture: Path | None = None
    mtconnect: Path | None = None
    audit: Path | None = None
    experiment: Path | None = None
    investigations: Path | None = None
    token: str | None = field(default=None, repr=False)
    evaluator: bool = False
    show_values: bool = False
    machine_label: str = "Authorized CNC"
    run_db: Path | None = None
    run_backend: Literal["sqlite", "postgres"] = "sqlite"
    run_database_url: str | None = field(default=None, repr=False)
    run_token: str | None = field(default=None, repr=False)
    review_token: str | None = field(default=None, repr=False)
    runs_enabled: bool = False
    evaluator_token: str | None = field(default=None, repr=False)
    memory_enabled: bool = False

    def __post_init__(self) -> None:
        """Reject insecure or ambiguous real-data deployments before serving."""
        # Variables:
        #   configured: Set when any private evidence source was supplied.
        configured = any(
            (
                self.capture,
                self.mtconnect,
                self.audit,
                self.experiment,
                self.investigations,
            )
        )
        if configured and (not self.token or len(self.token) < 24):
            raise ValueError(
                "CAPSTONE_UI_TOKEN must be at least 24 characters for configured files"
            )
        if self.run_backend not in ("sqlite", "postgres"):
            raise ValueError("Unsupported simulator journal backend")
        if (
            self.runs_enabled
            and self.run_backend == "postgres"
            and not self.run_database_url
        ):
            raise ValueError(
                "PostgreSQL journal requires CAPSTONE_UI_RUN_DATABASE_URL"
            )
        if self.runs_enabled:
            if (
                self.run_db is None
                or self.run_token is None
                or self.review_token is None
            ):
                raise ValueError(
                    "Simulator runs need a database and distinct operator/reviewer tokens"
                )
            tokens = (self.token, self.run_token, self.review_token)
            if any(len(token or "") < 24 for token in tokens) or len(set(tokens)) != 3:
                raise ValueError(
                    "Simulator tokens must be distinct, each at least 24 characters"
                )
        if (
            self.evaluator
            and self.runs_enabled
            and (
                not self.evaluator_token
                or len(self.evaluator_token) < 24
                or self.evaluator_token
                in (self.token, self.run_token, self.review_token)
            )
        ):
            raise ValueError(
                "Evaluator requires a distinct 24-character token when runs are enabled"
            )
        for path in (
            self.capture,
            self.mtconnect,
            self.audit,
            self.experiment,
            self.investigations,
            self.run_db,
        ):
            if path is not None and not path.is_absolute():
                raise ValueError(
                    "UI source paths must be absolute and configured server-side"
                )

    @classmethod
    def from_env(cls) -> "UiConfig":
        """Read only the explicit UI configuration names, never arbitrary settings."""

        # Variables:
        #   path: Convert a configured absolute path; unset remains unavailable.
        def path(key: str) -> Path | None:
            value = os.getenv(key, "").strip()
            return Path(value) if value else None

        return cls(
            capture=path("CAPSTONE_UI_CAPTURE"),
            mtconnect=path("CAPSTONE_UI_MTCONNECT"),
            audit=path("CAPSTONE_UI_CAPTURE_AUDIT"),
            experiment=path("CAPSTONE_UI_EXPERIMENTS"),
            investigations=path("CAPSTONE_UI_INVESTIGATIONS"),
            token=os.getenv("CAPSTONE_UI_TOKEN") or None,
            evaluator=os.getenv("CAPSTONE_UI_EVALUATOR") == "1",
            show_values=os.getenv("CAPSTONE_UI_SHOW_VALUES") == "1",
            machine_label=os.getenv("CAPSTONE_UI_MACHINE_LABEL", "Authorized CNC")[:80],
            run_db=path("CAPSTONE_UI_RUN_DB"),
            run_backend=os.getenv("CAPSTONE_UI_RUN_BACKEND", "sqlite"),
            run_database_url=os.getenv("CAPSTONE_UI_RUN_DATABASE_URL") or None,
            run_token=os.getenv("CAPSTONE_UI_RUN_TOKEN") or None,
            review_token=os.getenv("CAPSTONE_UI_REVIEW_TOKEN") or None,
            runs_enabled=os.getenv("CAPSTONE_UI_SIM_RUNS") == "1",
            evaluator_token=os.getenv("CAPSTONE_UI_EVALUATOR_TOKEN") or None,
            memory_enabled=os.getenv("CAPSTONE_UI_MEMORY_READ") == "1",
        )
