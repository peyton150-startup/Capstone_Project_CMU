"""Allowlisted sources for a single-host, read-only UI.

All paths come from the trusted server process environment, never from HTTP.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class UiConfig:
    # Variables:
    #   capture/audit/experiment/investigations: Privately approved local artifacts.
    #   token: Local browser-to-API authentication secret; never sent in responses.
    #   evaluator: Explicit opt-in for evaluator-only score views.
    #   show_values: Explicit opt-in for permitted raw sensor values.
    capture: Path | None = None
    audit: Path | None = None
    experiment: Path | None = None
    investigations: Path | None = None
    token: str | None = None
    evaluator: bool = False
    show_values: bool = False
    machine_label: str = "Authorized CNC"

    def __post_init__(self) -> None:
        """Reject insecure or ambiguous real-data deployments before serving."""
        # Variables:
        #   configured: Set when any private evidence source was supplied.
        configured = any((self.capture, self.audit, self.experiment, self.investigations))
        if configured and (not self.token or len(self.token) < 24):
            raise ValueError("CAPSTONE_UI_TOKEN must be at least 24 characters for configured files")
        for path in (self.capture, self.audit, self.experiment, self.investigations):
            if path is not None and not path.is_absolute():
                raise ValueError("UI source paths must be absolute and configured server-side")

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
            audit=path("CAPSTONE_UI_CAPTURE_AUDIT"),
            experiment=path("CAPSTONE_UI_EXPERIMENTS"),
            investigations=path("CAPSTONE_UI_INVESTIGATIONS"),
            token=os.getenv("CAPSTONE_UI_TOKEN") or None,
            evaluator=os.getenv("CAPSTONE_UI_EVALUATOR") == "1",
            show_values=os.getenv("CAPSTONE_UI_SHOW_VALUES") == "1",
            machine_label=os.getenv("CAPSTONE_UI_MACHINE_LABEL", "Authorized CNC")[:80],
        )
