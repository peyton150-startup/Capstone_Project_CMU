import ast
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

import capstone
from capstone.agent.artifacts import (
    AgentConclusion,
    DetectedAnomaly,
    ProposalRecord,
    TerminationReason,
    VerificationCheck,
)
from capstone.agent.state import InvestigationState

CAPSTONE = Path(capstone.__file__).parent  # wherever the package lives


def anomaly():
    return DetectedAnomaly(
        tick=40, machine_id="M2", kind="vibration_alarm", description="High vibration"
    )


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_only_one_completed_investigation_is_defined():
    defining = [
        path.relative_to(CAPSTONE).as_posix()
        for path in CAPSTONE.rglob("*.py")
        if "class CompletedInvestigation(" in path.read_text(encoding="utf-8")
    ]
    assert defining == ["contracts/completed_investigations.py"]


def test_the_old_reasoning_contract_is_gone():
    assert not (CAPSTONE / "contracts" / "completed.py").exists()


def test_runtime_records_stay_inside_the_agent_package():
    for path in CAPSTONE.rglob("*.py"):
        if path.parent.name != "agent":
            assert "capstone.agent.artifacts" not in imported_modules(path), path


def test_the_agent_package_does_not_import_memory_yet():
    for path in (CAPSTONE / "agent").glob("*.py"):
        modules = imported_modules(path)
        assert not any(m.startswith("capstone.memory") for m in modules), path


# Code that holds the simulator, its hidden truth or the score. The agent sees
# the factory only through its tools; one import of these would put the truth
# a line away from a prompt.
TRUTH_SIDE = (
    "capstone.simulator",
    "capstone.evaluation",
    "capstone.episode",
    "capstone.experiment",
    "capstone.evals",
)


def is_truth_side(module: str) -> bool:
    return any(module == side or module.startswith(side + ".") for side in TRUTH_SIDE)


def test_the_agent_package_does_not_import_truth_side_code():
    for path in (CAPSTONE / "agent").rglob("*.py"):
        found = sorted(m for m in imported_modules(path) if is_truth_side(m))
        assert not found, (path, found)


def test_the_truth_side_check_catches_a_forbidden_import(tmp_path):
    planted = tmp_path / "planted.py"
    planted.write_text(
        "import capstone.episode\n"
        "from capstone.simulator.ground_truth import GroundTruth\n"
        "from capstone.evaluation import scoring\n",
        encoding="utf-8",
    )
    found = {m for m in imported_modules(planted) if is_truth_side(m)}
    assert found == {
        "capstone.episode",
        "capstone.simulator.ground_truth",
        "capstone.evaluation",
    }
    assert not is_truth_side("capstone.simulatorish")
    assert not is_truth_side("capstone.tools.observation")


def test_runtime_records_reject_values_outside_their_limits():
    with pytest.raises(ValidationError):
        DetectedAnomaly(tick=-1, kind="alarm", description="x")
    with pytest.raises(ValidationError):
        AgentConclusion(diagnosis="worn", confidence=1.5, recommendation="intervene")
    with pytest.raises(ValidationError):
        AgentConclusion(diagnosis="worn", confidence=0.9, recommendation="ignore")
    with pytest.raises(ValidationError):
        ProposalRecord(machine_id="M2", action="x", reason="y", status="done")
    with pytest.raises(ValidationError):
        VerificationCheck(outcome="fixed", prediction="vibration falls")


def test_runtime_records_cannot_be_changed_or_extended():
    record = ProposalRecord(
        machine_id="M2", action="replace_bearing", reason="wear", status="pending"
    )
    with pytest.raises(ValidationError):
        record.status = "approved"
    with pytest.raises(ValidationError):
        ProposalRecord(
            machine_id="M2",
            action="replace_bearing",
            reason="wear",
            status="pending",
            approved_by="agent",
        )


def test_a_stop_reason_is_plain_text_for_the_shared_record():
    assert TerminationReason.MAX_TOOL_CALLS.value == "max_tool_calls"
    assert str(TerminationReason.TIMEOUT) == "timeout"


def test_working_memory_accepts_only_runtime_records():
    state = InvestigationState(
        run_id=UUID(int=1), investigation_id=UUID(int=2), anomaly=anomaly()
    )
    state.proposed_action = ProposalRecord(
        proposal_id=3, machine_id="M2", action="x", reason="y", status="rejected"
    )
    assert state.proposed_action.status == "rejected"
    with pytest.raises(ValidationError):
        state.conclusion = {"diagnosis": "worn", "confidence": 0.9}
    with pytest.raises(ValidationError):
        InvestigationState(
            run_id=UUID(int=1),
            investigation_id=UUID(int=2),
            anomaly={"summary": "High vibration", "symptoms": []},
        )
