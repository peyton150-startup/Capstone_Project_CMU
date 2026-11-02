# The machine manual as numbered sections, checked for leaks before use.
# Responsibility: read the manual's Markdown into sections; refuse hidden truth.
"""The manual's numbered sections, the unit the agent searches.

    sections = load_manual()            # §1.1 .. §2.15 of SIM-CNC-001
    check_no_leaks(sections)            # ValueError if one names a hidden fault

The manual (`sim-cnc-001.md`, beside this file) is written by the developer
about the machine type, never from a run. Only headings that start with
"## §" are sections; the cover, the directory and the provenance notes are
not, so they are never searched. Each section keeps its number and title,
so the agent can cite "§2.7".

A section must not carry anything the agent may not know: a fault's
internal name, a seed, a known-answer case ID, or the words "ground truth".
`check_no_leaks` refuses such a section, so a careless edit to the manual
cannot hand the agent an answer key.
"""

import re
from pathlib import Path

from capstone.contracts import Contract

MANUAL_PATH = Path(__file__).with_name("sim-cnc-001.md")
DOCUMENT_ID = "SIM-CNC-001"

_SECTION = re.compile(r"^## §(\d+\.\d+)\s+(.+?)\s*$", re.MULTILINE)
_HEADING = re.compile(r"^## ", re.MULTILINE)
_REVISION = re.compile(r"\*\*Revision:\*\*\s*([\d.]+)")

# What a section must never contain: the simulator's internal fault names,
# its hidden-state vocabulary, seeds and known-answer case IDs.
_LEAKS = re.compile(
    r"bearing_degradation|bad_material_batch|wrong_setting|false_alarm"
    r"|sensor_drift|sensor_dropout|servo_drive_wear|hydraulic_leak"
    r"|ground[ _]truth|hidden state"
    r"|\bseed\b|\bKA-\d",
    re.IGNORECASE,
)


class ManualSection(Contract):
    """One numbered section of the manual."""

    section_id: str  # "2.7"
    title: str
    text: str
    document_id: str = DOCUMENT_ID
    revision: str

    @property
    def citation(self) -> str:
        """How the agent should cite it: "SIM-CNC-001 §2.7"."""
        return f"{self.document_id} §{self.section_id}"


def parse_manual(markdown: str) -> tuple[ManualSection, ...]:
    """The numbered sections, in order. Anything under another heading is left out."""
    # Variables:
    #   markdown: The manual's full text.
    #   found: The revision line, if the manual has one.
    #   revision: The manual's revision number, or 'unknown'.
    #   following: The next heading, which ends the section.
    #   body: The section's text, up to that heading.
    found = _REVISION.search(markdown)
    revision = found.group(1) if found else "unknown"
    sections = []
    for match in _SECTION.finditer(markdown):
        following = _HEADING.search(markdown, match.end())
        body = markdown[match.end() : following.start() if following else None]
        sections.append(
            ManualSection(
                section_id=match.group(1),
                title=match.group(2),
                text=" ".join(body.replace("**", "").split()),
                revision=revision,
            )
        )
    return tuple(sections)


def check_no_leaks(sections: tuple[ManualSection, ...]) -> None:
    """ValueError naming each section that carries something the agent may not know."""
    # Variables:
    #   leaking: Each section that contains a fault name, a seed or similar hidden
    #     detail.
    leaking = [
        f"§{s.section_id} ({found.group(0)!r})"
        for s in sections
        if (found := _LEAKS.search(f"{s.title} {s.text}"))
    ]
    if leaking:
        raise ValueError("manual sections leak hidden truth: " + ", ".join(leaking))


def load_manual(path: Path = MANUAL_PATH) -> tuple[ManualSection, ...]:
    """The manual's sections, checked for leaks."""
    sections = parse_manual(path.read_text(encoding="utf-8"))
    if not sections:
        raise ValueError(f"no numbered sections in {path}")
    check_no_leaks(sections)
    return sections
