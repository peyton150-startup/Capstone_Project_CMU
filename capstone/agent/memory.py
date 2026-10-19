"""Basic memory: one JSON record per finished investigation, and a look-up of similar ones.

Holds only what the agent itself saw or decided: the anomaly, the
evidence it fetched, its last hypothesis table, its conclusion, the
actions approved, and the outcome as the factory reported it (the
technician's findings after maintenance). Never the evaluation score or
the ground truth, so a later investigation cannot learn the answer key.
"""

import json
import re
from pathlib import Path

from capstone.agent.toolbox import _schema

SEARCH_SPEC = {
    "name": "search_incident_history",
    "description": "Past investigations most similar to a description (symptoms, machine, sensor words). "
    "Returns their anomaly, conclusion, action and outcome. Past conclusions may have been wrong.",
    "input_schema": _schema(
        {
            "query": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 10},
        },
        ["query"],
    ),
}

_WORD = re.compile(r"[a-z]+")
_IGNORED = {
    "the",
    "a",
    "an",
    "of",
    "on",
    "in",
    "and",
    "to",
    "is",
    "was",
    "for",
    "tick",
    "at",
    "by",
    "with",
}


def _words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _IGNORED}


class InvestigationMemory:
    def __init__(self, path: str | Path | None = None):
        """With a path, records are appended to a JSON-lines file and read back from it; without, kept in memory."""
        self.path = Path(path) if path else None
        self.records: list[dict] = []
        if self.path and self.path.exists():
            self.records = [
                json.loads(line)
                for line in self.path.read_text().splitlines()
                if line.strip()
            ]

    def tools(self) -> dict:
        return {"search_incident_history": (SEARCH_SPEC, self.search)}

    def record(
        self, *, anomaly: str, notebook, proposals: list[dict], outcome: list[str]
    ) -> dict:
        diagnosis = notebook.diagnosis
        entry = {
            "id": len(self.records) + 1,
            "anomaly": anomaly,
            "evidence": [
                c
                for c in notebook.calls
                if c["name"] not in ("update_hypotheses", "submit_diagnosis")
            ],
            "hypotheses": notebook.hypotheses,
            "conclusion": diagnosis.model_dump() if diagnosis else None,
            "actions": [
                f"{p['action']} {p['machine_id']}"
                for p in proposals
                if p["status"] == "approved"
            ],
            "outcome": outcome,
        }
        self.records.append(entry)
        if self.path:
            with self.path.open("a") as file:
                file.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def search(self, query: str, limit: int = 3) -> list[dict]:
        """Rank past investigations by shared words with the query (anomaly, conclusion and outcome)."""
        wanted = _words(query)
        ranked = []
        for entry in self.records:
            conclusion = entry["conclusion"] or {}
            text = " ".join(
                [
                    entry["anomaly"],
                    *(str(v) for v in conclusion.values() if v),
                    *entry["outcome"],
                ]
            )
            overlap = len(wanted & _words(text))
            if overlap:
                ranked.append((-overlap, -entry["id"], entry))
        return [
            {
                "investigation": e["id"],
                "anomaly": e["anomaly"],
                "conclusion": e["conclusion"],
                "actions": e["actions"],
                "outcome": e["outcome"],
            }
            for _, _, e in sorted(ranked, key=lambda r: r[:2])[:limit]
        ]
