"""The fault-pack registry (`capstone/faults.py`): one place per fault."""

from dataclasses import fields
from pathlib import Path
from typing import get_args

import pytest

from capstone.baseline import FIX
from capstone.evaluation.scoring import CAUSE_KINDS, CORRECT_ACTION, RELEVANT_EVIDENCE
from capstone.faults import (
    ACTIONS,
    BY_KIND,
    FAULT_KINDS,
    PACKS,
    AgentSide,
    FaultPlace,
    agent_side,
)
from capstone.simulator.generator import FAULTS, build_scenario
from capstone.simulator.line import build_line
from capstone.tools import actions, diagnosis

CODE = Path(__file__).resolve().parents[1] / "capstone-code" / "capstone"


def test_every_fault_is_named_once():
    kinds = [pack.kind for pack in PACKS]
    assert len(kinds) == len(set(kinds)) == len(BY_KIND)


def test_every_list_of_faults_is_built_from_the_packs():
    kinds = tuple(pack.kind for pack in PACKS)
    assert FAULTS == FAULT_KINDS == diagnosis.FAULT_KINDS == kinds
    assert get_args(diagnosis.FaultKind) == kinds
    assert set(CORRECT_ACTION) == set(RELEVANT_EVIDENCE) == set(kinds)
    assert actions.ACTIONS == ACTIONS


def test_the_lists_keep_the_values_they_had_before_the_registry():
    """The values the hand-written lists held on 2026-10-26, before the move."""
    assert FAULTS == (
        "bearing_degradation",
        "bad_material_batch",
        "wrong_setting",
        "false_alarm",
    )
    assert ACTIONS == ("replace_bearing", "reset_setting")
    assert CORRECT_ACTION == {
        "bearing_degradation": "replace_bearing",
        "wrong_setting": "reset_setting",
        "bad_material_batch": None,
        "false_alarm": None,
    }
    assert set(CAUSE_KINDS) == {
        "bearing_degradation",
        "wrong_setting",
        "bad_material_batch",
    }
    assert FIX == {
        "bearing_degradation": "replace_bearing",
        "wrong_setting": "reset_setting",
    }


def test_a_correct_action_is_one_the_desk_knows_and_only_causes_need_one():
    for pack in PACKS:
        action = pack.evaluator.correct_action
        assert action is None or action in ACTIONS
        if action is not None:
            assert pack.evaluator.is_cause


def test_every_pack_has_a_difficulty_and_relevant_evidence():
    for pack in PACKS:
        assert pack.difficulty in ("easy", "medium", "hard")
        assert pack.evaluator.relevant


def test_the_agent_side_holds_only_a_name_and_a_repair():
    assert [f.name for f in fields(AgentSide)] == ["kind", "action"]
    assert all(isinstance(side, AgentSide) for side in agent_side())


@pytest.mark.parametrize("package", ["agent", "tools", "providers"])
def test_agent_facing_code_never_reads_the_evaluator_side(package):
    """Static guard: only scoring may touch evaluator-only fault data."""
    for path in (CODE / package).rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert ".evaluator" not in text, path
        assert "PACKS" not in text and "BY_KIND" not in text, path


@pytest.mark.parametrize("pack", PACKS, ids=lambda pack: pack.kind)
def test_every_pack_builds_its_own_fault(pack):
    sim = build_line(4, machines=3)
    pick = sim.rng.stream("generator")
    sim.add_scenario(pack.build(sim, pick, FaultPlace("CNC-02", 300)))
    (truth,) = sim.ground_truth()
    assert truth.fault == pack.kind


def test_the_seed_contract_is_unchanged():
    """Seeds 0-9, as the generator built them before the registry (2026-10-26).

    The order of PACKS is part of this contract: reordering it changes
    which fault each seed gets, and every saved result with it.
    """
    built = []
    for seed in range(10):
        (t,) = build_scenario(seed).ground_truth()
        built.append((seed, t.fault, t.machine_id, t.batch_id, t.start_tick))
    assert built == [
        (0, "false_alarm", "CNC-03", None, 523),
        (1, "wrong_setting", "CNC-04", None, 399),
        (2, "bearing_degradation", "CNC-04", None, 348),
        (3, "bad_material_batch", None, 2, None),
        (4, "false_alarm", "CNC-04", None, 416),
        (5, "bad_material_batch", None, 3, None),
        (6, "wrong_setting", "CNC-02", None, 363),
        (7, "bad_material_batch", None, 2, None),
        (8, "false_alarm", "CNC-01", None, 521),
        (9, "bad_material_batch", None, 2, None),
    ]
