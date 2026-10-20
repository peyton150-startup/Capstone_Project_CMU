# The scenarios that change the factory: production, ambient, and faults.
# Responsibility: change the true state over time, never the sensor readings.
import math
from abc import ABC, abstractmethod

from capstone.simulator.ground_truth import GroundTruth
from capstone.simulator.rng import RandomSource
from capstone.simulator.state import (
    NORMAL_LOAD,
    FactoryState,
    Inspection,
    Job,
    MachineStatus,
    MaterialBatch,
)


class Scenario(ABC):
    """Changes reality over time. Never writes evidence.

    `apply` is handed the factory state and the tick, nothing else, so a
    scenario cannot reach the reading log or the event log. Whatever it
    causes becomes visible only when sensors read the state it changed.

    Each scenario owns one RNG stream named `scenario.<name>`. That name
    is part of the seed; it is a frozen contract.
    """

    def __init__(self, name: str, rng: RandomSource):
        self.name = name
        self.stream_name = f"scenario.{name}"
        self._stream = rng.stream(self.stream_name)

    @abstractmethod
    def apply(self, state: FactoryState, tick: int) -> None: ...

    @abstractmethod
    def ground_truth(self) -> GroundTruth | None:
        """The real story, from this scenario's own settings, not from state.

        None for normal factory life that is not a fault.
        """


class BearingDegradation(Scenario):
    """Wears one machine's bearing from `start_tick` on, while it runs.

    Changes `bearing_health` and nothing else. It knows nothing about
    vibration or any other sensor: the symptoms come from sensors reading
    the health it lowers.

    Wear scales with (load / normal load) ** load_exponent; bearing life
    falls roughly with the cube of load. It reads `load`, never writes it.
    A machine set to run faster than standard wears faster in the same
    way, by speed ratio ** speed_exponent.
    """

    def __init__(
        self,
        name: str,
        rng: RandomSource,
        *,
        machine_id: str,
        start_tick: int,
        rate: float,
        variation: float = 0.5,
        load_exponent: float = 3.0,
        speed_exponent: float = 3.0,
    ):
        if rate <= 0:
            raise ValueError("rate must be positive")
        if not 0.0 <= variation < 1.0:
            raise ValueError("variation must be in [0, 1)")
        super().__init__(name, rng)
        self.machine_id = machine_id
        self.start_tick = start_tick
        self.rate = rate
        self.variation = variation
        self.load_exponent = load_exponent
        self.speed_exponent = speed_exponent

    def apply(self, state: FactoryState, tick: int) -> None:
        if tick < self.start_tick:
            return
        # Drawn before the status check so the stream's position depends
        # only on ticks since start, not on the machine's status history.
        loss = self.rate * self._stream.uniform(
            1.0 - self.variation, 1.0 + self.variation
        )
        machine = state.machines[self.machine_id]
        replaced = machine.bearing_replaced_tick
        if replaced is not None and replaced >= self.start_tick:
            return  # the bearing this fault was wearing has been replaced: the fault is over
        if machine.status is not MachineStatus.RUNNING:
            return
        loss *= (machine.load / NORMAL_LOAD) ** self.load_exponent
        loss *= machine.speed_ratio**self.speed_exponent
        machine.condition.bearing_health = max(
            0.0, machine.condition.bearing_health - loss
        )

    def ground_truth(self) -> GroundTruth:
        return GroundTruth(
            scenario=self.name,
            fault="bearing_degradation",
            machine_id=self.machine_id,
            start_tick=self.start_tick,
        )


class WrongSetting(Scenario):
    """Someone sets one machine to the wrong speed at `start_tick`.

    Changes that machine's `speed_setting`, once, and nothing else. The
    machine's hardware is sound. What follows (quicker or slower jobs,
    a little more or less vibration and heat, more rejects) comes from
    the machine's own physics reading the setting. It writes once so that
    a later correction stays corrected.
    """

    def __init__(
        self,
        name: str,
        rng: RandomSource,
        *,
        machine_id: str,
        start_tick: int,
        factor: float,
    ):
        if factor <= 0 or factor == 1.0:
            raise ValueError(
                "factor must be positive and not 1 (1 is the standard setting)"
            )
        super().__init__(name, rng)
        self.machine_id = machine_id
        self.start_tick = start_tick
        self.factor = factor
        self._done = False

    def apply(self, state: FactoryState, tick: int) -> None:
        if self._done or tick < self.start_tick:
            return
        machine = state.machines[self.machine_id]
        machine.speed_setting = machine.standard_speed * self.factor
        self._done = True

    def ground_truth(self) -> GroundTruth:
        return GroundTruth(
            scenario=self.name,
            fault="wrong_setting",
            machine_id=self.machine_id,
            start_tick=self.start_tick,
        )


class BadMaterialBatch(Scenario):
    """One batch of raw material is poor: jobs cut from it fail inspection more often.

    Changes that batch's hidden `defect_risk` and nothing else. No machine
    is at fault and no sensor moves. The failures come from the ordinary
    inspection reading the risk each job started with, and stop by
    themselves once the batch is used up.

    The first batch cannot be the bad one: its first job is cut on the
    same tick it is opened, before a fault added after the line has run.
    """

    def __init__(
        self,
        name: str,
        rng: RandomSource,
        *,
        batch_number: int,
        added_risk: float = 0.30,
    ):
        if batch_number < 2:
            raise ValueError("batch_number must be 2 or more")
        if not 0.0 < added_risk <= 1.0:
            raise ValueError("added_risk must be above 0 and at most 1")
        super().__init__(name, rng)
        self.batch_number = batch_number
        self.added_risk = added_risk

    def apply(self, state: FactoryState, tick: int) -> None:
        batch = state.batch
        if batch is not None and batch.id == self.batch_number:
            batch.defect_risk = self.added_risk

    def ground_truth(self) -> GroundTruth:
        return GroundTruth(
            scenario=self.name, fault="bad_material_batch", batch_id=self.batch_number
        )


class FalseAlarm(Scenario):
    """One machine's vibration sensor misreads for a few ticks, then recovers by itself.

    Writes only the sensor's hidden offset: on at `start_tick`, off again
    `duration` ticks later. The machine itself is untouched, so nothing
    but that one sensor moves, and the right response is to do nothing.
    The offset reaches the reading through the sensor, never as a written
    reading, so the alarm that trips is an ordinary alarm.
    """

    def __init__(
        self,
        name: str,
        rng: RandomSource,
        *,
        machine_id: str,
        start_tick: int,
        duration: int = 5,
        offset: float = 5.0,
    ):
        if duration < 1:
            raise ValueError("duration must be at least 1 tick")
        if offset <= 0:
            raise ValueError("offset must be positive")
        super().__init__(name, rng)
        self.machine_id = machine_id
        self.start_tick = start_tick
        self.duration = duration
        self.offset = offset

    def apply(self, state: FactoryState, tick: int) -> None:
        if tick < self.start_tick:
            return
        glitching = tick < self.start_tick + self.duration
        state.machines[self.machine_id].condition.vibration_sensor_offset = (
            self.offset if glitching else 0.0
        )

    def ground_truth(self) -> GroundTruth:
        return GroundTruth(
            scenario=self.name,
            fault="false_alarm",
            machine_id=self.machine_id,
            start_tick=self.start_tick,
        )


DEFECT_BASELINE = 0.01  # one job in a hundred fails inspection on a perfect line
DEFECT_FROM_WEAR = 0.45  # extra chance a completely worn machine would add
DEFECT_FROM_SETTING = (
    8.0  # times the squared distance from standard speed: 15% off adds 0.18
)
WORN_SLOWDOWN = 0.4  # a completely worn bearing would cost 40% of working speed


def working_speed(machine) -> float:
    """Ticks of work a running machine gets done per tick. 1.0 when healthy and set right.

    Part of the machine's own physics, whatever damaged the bearing or
    changed the setting. Wear is slow-then-fast, like vibration: early
    wear barely shows. The speed setting scales it directly.
    """
    wear = 1.0 - machine.condition.bearing_health
    return (1.0 - WORN_SLOWDOWN * wear**2) * machine.speed_ratio


def defect_mark(machine) -> float:
    """What this machine adds to a job's defect risk as it finishes its part."""
    wear = 1.0 - machine.condition.bearing_health
    return (
        DEFECT_FROM_WEAR * wear**2
        + DEFECT_FROM_SETTING * (machine.speed_ratio - 1.0) ** 2
    )


class ProductionLine(Scenario):
    """Normal factory life: jobs enter at the first machine and move down the line.

    How long a job takes is a property of each machine (`ticks_per_job`),
    not of the job; a job brings only its load. `time_variation` adds a
    few ticks either way to each job at each machine, so no two jobs take
    quite the same time. A worn machine gets less than a tick of work
    done per tick, so its jobs take longer, and leaves each job with a
    higher chance of failing the inspection at the end of the line.
    Inspections draw from their own stream, `scenario.<name>.inspection`.

    With `jobs_per_batch` set, jobs are cut from numbered material
    batches. A job carries its batch number and starts with whatever
    defect risk the batch has. The next batch is opened the moment the
    last job is cut from the current one, so it is in place, and can be
    changed by a later scenario, before any job is cut from it.

    Each tick, in two passes. Movement, from the last machine back to the
    first: a finished job moves on if the next machine is free and not
    down, or leaves the line at the end; a new job enters whenever the
    first machine is free. Then work: a machine with unfinished work runs
    at its job's load, and any other machine is idle. A machine that is
    down is left alone and keeps its job, which blocks everything behind
    it. Not a fault, so no ground truth.

    Add it before any scenario that reads `load` or status, so that
    scenario sees this tick's work.
    """

    def __init__(
        self,
        name: str,
        rng: RandomSource,
        *,
        machine_ids: list[str],
        min_load: float = 0.3,
        max_load: float = 0.8,
        time_variation: int = 0,
        jobs_per_batch: int = 0,
    ):
        if jobs_per_batch < 0:
            raise ValueError("jobs_per_batch cannot be negative")
        if not machine_ids or len(set(machine_ids)) != len(machine_ids):
            raise ValueError("the line needs at least one machine, each listed once")
        if not 0.0 <= min_load <= max_load <= 1.0:
            raise ValueError("need 0 <= min_load <= max_load <= 1")
        if time_variation < 0:
            raise ValueError("time_variation cannot be negative")
        super().__init__(name, rng)
        self.machine_ids = list(machine_ids)
        self.time_variation = time_variation
        self.jobs_per_batch = jobs_per_batch
        self._inspection_stream = rng.stream(f"{self.stream_name}.inspection")
        self.min_load, self.max_load = min_load, max_load

    def apply(self, state: FactoryState, tick: int) -> None:
        if state.lines.get(self.name) != self.machine_ids:
            taken = {
                m
                for name, order in state.lines.items()
                if name != self.name
                for m in order
            }
            if taken & set(self.machine_ids):
                raise ValueError(f"{self.name}: a machine cannot be on two lines")
            state.lines[self.name] = list(self.machine_ids)
        line = [state.machines[machine_id] for machine_id in self.machine_ids]
        self._move_jobs(state, line, tick)
        for machine in line:
            if machine.status is MachineStatus.DOWN:
                continue
            if machine.job is not None and not machine.job_done:
                machine.status = MachineStatus.RUNNING
                machine.load = machine.job.load
                machine.job_progress += working_speed(machine)
                if machine.job_done:  # this machine's part is finished: wear or a wrong setting leaves a mark
                    machine.job.defect_risk += defect_mark(machine)
            else:
                machine.status = MachineStatus.IDLE
                machine.load = 0.0

    def _move_jobs(self, state: FactoryState, line: list, tick: int) -> None:
        for position in reversed(range(len(line))):
            machine = line[position]
            if machine.status is MachineStatus.DOWN or machine.job is None:
                continue
            if not machine.job_done:
                continue
            if position == len(line) - 1:
                state.completed_jobs.append(machine.job.id)
                chance_of_failing = min(0.95, DEFECT_BASELINE + machine.job.defect_risk)
                passed = self._inspection_stream.random() >= chance_of_failing
                state.inspections.append(
                    Inspection(
                        job_id=machine.job.id,
                        tick=tick,
                        passed=passed,
                        batch_id=machine.job.batch_id,
                    )
                )
            else:
                following = line[position + 1]
                if following.job is not None or following.status is MachineStatus.DOWN:
                    continue  # nowhere to go: the finished job waits here
                self._place(machine.job, following)
            machine.job, machine.job_progress, machine.job_work = None, 0.0, None
        first = line[0]
        if first.job is None and first.status is not MachineStatus.DOWN:
            job = Job(
                id=state.next_job_id,
                load=self._stream.uniform(self.min_load, self.max_load),
            )
            if self.jobs_per_batch:
                self._cut_from_batch(state, job)
            self._place(job, first)
            state.next_job_id += 1

    def _cut_from_batch(self, state: FactoryState, job: Job) -> None:
        if state.batch is None:
            state.batch = MaterialBatch(id=1, jobs_left=self.jobs_per_batch)
        batch = state.batch
        job.batch_id = batch.id
        job.defect_risk = (
            batch.defect_risk
        )  # the material's share; machines add theirs later
        batch.jobs_left -= 1
        if batch.jobs_left == 0:
            state.batch = MaterialBatch(id=batch.id + 1, jobs_left=self.jobs_per_batch)

    def _place(self, job: Job, machine) -> None:
        machine.job, machine.job_progress, machine.job_work = job, 0.0, None
        if self.time_variation:
            extra = self._stream.randint(-self.time_variation, self.time_variation)
            machine.job_work = max(1, machine.ticks_per_job + extra)

    def ground_truth(self) -> None:
        return None


class AmbientTemperature(Scenario):
    """Normal factory life: the air warms through the day and cools overnight.

    A daily cycle plus a slow drift, so no two days are quite alike. One
    value for the whole factory. Not a fault, so no ground truth.
    `warmest_tick` is the tick of the first afternoon peak; the default
    suits a run that starts at 6 am with one-minute ticks (peak at 4 pm).
    """

    def __init__(
        self,
        name: str,
        rng: RandomSource,
        *,
        mean: float = 73.0,
        swing: float = 4.5,
        ticks_per_day: int = 1440,
        warmest_tick: int = 600,
        drift_step: float = 0.03,
        drift_pull: float = 0.001,
    ):
        super().__init__(name, rng)
        self.mean, self.swing = mean, swing
        self.ticks_per_day, self.warmest_tick = ticks_per_day, warmest_tick
        self.drift_step, self.drift_pull = drift_step, drift_pull
        self._drift = 0.0

    def apply(self, state: FactoryState, tick: int) -> None:
        self._drift = (1.0 - self.drift_pull) * self._drift + self._stream.gauss(
            0.0, self.drift_step
        )
        time_of_day = 2.0 * math.pi * (tick - self.warmest_tick) / self.ticks_per_day
        state.ambient_temperature = (
            self.mean + self.swing * math.cos(time_of_day) + self._drift
        )

    def ground_truth(self) -> None:
        return None


class LoadingDoor(Scenario):
    """Normal factory life: the loading door opens now and then and lets cool air in.

    Always a cooling, whatever the season. It writes the door and the
    door's own cooling, never the building temperature, so it does not
    matter whether it runs before or after AmbientTemperature. Not a
    fault, so no ground truth.
    """

    def __init__(
        self,
        name: str,
        rng: RandomSource,
        *,
        cooling: float = 5.0,
        chance_per_tick: float = 1 / 300,
        min_open: int = 5,
        max_open: int = 20,
        cool_per_tick: float = 0.5,
        recover_per_tick: float = 0.2,
    ):
        if not 1 <= min_open <= max_open:
            raise ValueError("need 1 <= min_open <= max_open")
        if cooling < 0 or not 0.0 <= chance_per_tick <= 1.0:
            raise ValueError("cooling must be >= 0 and chance_per_tick within 0..1")
        super().__init__(name, rng)
        self.cooling = cooling
        self.chance_per_tick = chance_per_tick
        self.min_open, self.max_open = min_open, max_open
        self.cool_per_tick, self.recover_per_tick = cool_per_tick, recover_per_tick
        self._closes_at = 0

    def apply(self, state: FactoryState, tick: int) -> None:
        # One draw every tick, so the stream's position depends only on the tick.
        opens = self._stream.random() < self.chance_per_tick
        if state.door_open:
            if tick >= self._closes_at:
                state.door_open = False
        elif opens:
            state.door_open = True
            self._closes_at = tick + self._stream.randint(self.min_open, self.max_open)
        if state.door_open:
            state.door_cooling = min(
                self.cooling, state.door_cooling + self.cool_per_tick
            )
        else:
            state.door_cooling = max(0.0, state.door_cooling - self.recover_per_tick)

    def ground_truth(self) -> None:
        return None
