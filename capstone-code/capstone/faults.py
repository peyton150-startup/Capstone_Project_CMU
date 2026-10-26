"""Fault packs: every fault the factory can have, described once.

Before this registry, each fault was named in about nine lists across seven
files (the generator's fault list, the diagnosis kinds, the repair actions,
the correct action, the relevant evidence, the cause kinds, the baseline's
fixes...), and a fault missing from one of them was half wired. Now each
fault is one `FaultPack` in `PACKS`, and those lists are built from it.

A pack has three parts, kept apart on purpose:

- `agent`: what the investigating agent may know. The name it can give the
  cause in its diagnosis, and the repair action (if any) the pack adds to
  the approval desk. Only this part may feed prompts and tool descriptions
  (`agent_side`).
- `evaluator`: what only scoring may know. The correct action, whether the
  fault is a cause to fix or name, and the evidence that bears on it.
  Never shown to the agent.
- `build`: simulator code that adds the fault's scenario to a factory,
  drawing its strength from the generator's stream.

`difficulty` tags each pack for the easy / medium / hard modes. Nothing reads
it yet: the mode switch waits for the scored single-agent run (developer's
decision, 2026-10-26). The tags are the coding agent's proposal, for the
developer to confirm.

Packs are fixed in code, never added or removed while the program runs, so
the same seed always builds the same factory. The order of `PACKS` is part
of the seed contract: `build_scenario` draws a fault from it, so reordering
it would change which fault every seed gets.
"""

import random
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal

from capstone.simulator.scenarios import (
    BadMaterialBatch,
    BearingDegradation,
    FalseAlarm,
    Scenario,
    WrongSetting,
)
from capstone.simulator.simulator import Simulator

Difficulty = Literal["easy", "medium", "hard"]

# How fast a worn bearing progresses. "compressed" is the original curve (fault
# start to failure in about 9-28 hours of running), kept as the default so every
# existing case and result stays the same. "three_day" follows the engineering
# feedback of 2026-10-23: a quiet stretch first, then a visible ramp from onset
# to failure of about three operating days (4,320 one-minute ticks of running).
BEARING_PROFILES = ("compressed", "three_day")
# three_day: the same seeded rate draw, scaled so that the median onset-to-failure
# time is about 4,320 running ticks (measured on seeds 1-40,
# docs/benchmarks/2026-10-26-bearing-three-day.md).
THREE_DAY_RATE_SCALE = 0.17
THREE_DAY_ONSET_HEALTH = 0.8  # below this, vibration starts to stand out of the noise
THREE_DAY_QUIET_FACTOR = 0.5  # before onset, wear runs at half the rate


# The tools that read one machine sensor, by any route.
SENSOR_TOOLS = ("get_readings", "get_sensor_trend", "get_sensor_summary")


@dataclass(frozen=True)
class Relevant:
    """One kind of evidence that bears on a fault. Evaluator-side only."""

    label: str
    tools: tuple[str, ...]
    sensor: str | None = None  # the sensor the call must name, if any
    on_machine: bool = False  # the call must be about the faulty machine

    def describe(self, machine_id: str | None) -> str:
        return self.label.format(machine=machine_id)

    def met_by(self, tool: str, arguments: Mapping, machine_id: str | None) -> bool:
        if tool not in self.tools:
            return False
        if self.sensor is not None and arguments.get("sensor") != self.sensor:
            return False
        if self.on_machine:
            # An event query for the whole factory also covers the machine.
            named = arguments.get("machine_id")
            whole_factory = tool == "get_events" and named is None
            return named == machine_id or whole_factory
        return True


@dataclass(frozen=True)
class FaultPlace:
    """Where and when a seeded fault happens, drawn before its pack builds it."""

    machine_id: str
    start_tick: int
    bearing_profile: str = "compressed"


@dataclass(frozen=True)
class AgentSide:
    """What the agent may know about a fault: never its effects or its fix."""

    kind: str  # the name a diagnosis gives this cause
    action: str | None  # the repair this pack adds to the approval desk, if any


@dataclass(frozen=True)
class EvaluatorSide:
    """What only scoring may know. Never reaches a prompt or a tool."""

    correct_action: str | None  # None: leave the factory alone
    is_cause: bool  # False: a distractor when other faults are present
    relevant: tuple[Relevant, ...]


# Adds the fault's scenario to the factory, drawing from the generator stream.
Builder = Callable[[Simulator, random.Random, FaultPlace], Scenario]


@dataclass(frozen=True)
class FaultPack:
    agent: AgentSide
    evaluator: EvaluatorSide
    difficulty: Difficulty
    build: Builder

    @property
    def kind(self) -> str:
        return self.agent.kind


def _bearing(sim: Simulator, pick: random.Random, place: FaultPlace) -> Scenario:
    rate = pick.uniform(0.0004, 0.0008)
    phases = {}
    if place.bearing_profile == "three_day":
        rate *= THREE_DAY_RATE_SCALE
        phases = {
            "onset_health": THREE_DAY_ONSET_HEALTH,
            "quiet_factor": THREE_DAY_QUIET_FACTOR,
        }
    return BearingDegradation(
        "fault",
        sim.rng,
        machine_id=place.machine_id,
        start_tick=place.start_tick,
        rate=rate,
        **phases,
    )


def _bad_batch(sim: Simulator, pick: random.Random, place: FaultPlace) -> Scenario:
    batch = pick.randint(2, 3)
    risk = pick.uniform(0.35, 0.50)
    return BadMaterialBatch("fault", sim.rng, batch_number=batch, added_risk=risk)


def _wrong_setting(sim: Simulator, pick: random.Random, place: FaultPlace) -> Scenario:
    factor = pick.choice((0.80, 0.82, 1.18, 1.20))
    return WrongSetting(
        "fault",
        sim.rng,
        machine_id=place.machine_id,
        start_tick=place.start_tick,
        factor=factor,
    )


def _false_alarm(sim: Simulator, pick: random.Random, place: FaultPlace) -> Scenario:
    duration = pick.randint(3, 8)
    return FalseAlarm(
        "fault",
        sim.rng,
        machine_id=place.machine_id,
        start_tick=place.start_tick,
        duration=duration,
    )


# Order is part of the seed contract (see the module docstring).
PACKS: tuple[FaultPack, ...] = (
    FaultPack(
        agent=AgentSide(kind="bearing_degradation", action="replace_bearing"),
        evaluator=EvaluatorSide(
            correct_action="replace_bearing",
            is_cause=True,
            relevant=(
                Relevant("vibration of {machine}", SENSOR_TOOLS, "vibration", True),
                Relevant("temperature of {machine}", SENSOR_TOOLS, "temperature", True),
                Relevant("events of {machine}", ("get_events",), on_machine=True),
            ),
        ),
        difficulty="easy",  # a vibration alarm points at the machine
        build=_bearing,
    ),
    FaultPack(
        agent=AgentSide(kind="bad_material_batch", action=None),
        evaluator=EvaluatorSide(
            correct_action=None,
            is_cause=True,
            relevant=(
                Relevant("inspection results", ("get_inspections",)),
                Relevant("events (material batches)", ("get_events",)),
                Relevant("a job's history", ("get_job_history",)),
            ),
        ),
        difficulty="medium",  # no alarm; rejects must be traced to a batch
        build=_bad_batch,
    ),
    FaultPack(
        agent=AgentSide(kind="wrong_setting", action="reset_setting"),
        evaluator=EvaluatorSide(
            correct_action="reset_setting",
            is_cause=True,
            relevant=(
                Relevant("machine settings", ("get_settings",)),
                Relevant("inspection results", ("get_inspections",)),
                Relevant("vibration of {machine}", SENSOR_TOOLS, "vibration", True),
            ),
        ),
        difficulty="medium",  # no alarm; speeds differ per machine
        build=_wrong_setting,
    ),
    FaultPack(
        agent=AgentSide(kind="false_alarm", action=None),
        evaluator=EvaluatorSide(
            correct_action=None,
            is_cause=False,
            relevant=(
                Relevant("vibration of {machine}", SENSOR_TOOLS, "vibration", True),
                Relevant("events of {machine}", ("get_events",), on_machine=True),
            ),
        ),
        difficulty="easy",  # a short spike that falls away
        build=_false_alarm,
    ),
)

BY_KIND: dict[str, FaultPack] = {pack.kind: pack for pack in PACKS}


def agent_side() -> tuple[AgentSide, ...]:
    """The only view of the packs that agent-facing code may use."""
    return tuple(pack.agent for pack in PACKS)


# Built from the packs, under the names the rest of the code already uses.
FAULT_KINDS: tuple[str, ...] = tuple(side.kind for side in agent_side())
ACTIONS: tuple[str, ...] = tuple(
    side.action for side in agent_side() if side.action is not None
)
