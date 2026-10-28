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
        # Variables:
        #   name: What this scenario is called; it is also part of its random stream's
        #     name.
        #   rng: The factory's random source, which hands out this scenario's own
        #     stream.
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

    Two phases (optional): while health is above `onset_health`, wear runs
    at `quiet_factor` times the rate, so the bearing wears quietly before
    the damage starts to show; below it, at the full rate. The defaults
    (1.0 and 1.0) give one phase, the original behaviour.
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
        onset_health: float = 1.0,
        quiet_factor: float = 1.0,
    ):
        # Variables:
        #   machine_id: The machine whose bearing wears.
        #   start_tick: When the wear begins.
        #   rate: Health lost per running tick at normal load and speed.
        #   variation: How much the loss varies from tick to tick, as a fraction of the
        #     rate.
        #   load_exponent: How steeply a heavier load wears faster; 3 means the cube.
        #   speed_exponent: How steeply a faster-than-standard setting wears faster.
        #   onset_health: Health at which damage starts to show; above it wear is quiet.
        #   quiet_factor: Wear speed relative to normal while health is above
        #     onset_health.
        if rate <= 0:
            raise ValueError("rate must be positive")
        if not 0.0 <= variation < 1.0:
            raise ValueError("variation must be in [0, 1)")
        if not 0.0 < onset_health <= 1.0:
            raise ValueError("onset_health must be in (0, 1]")
        if not 0.0 < quiet_factor <= 1.0:
            raise ValueError("quiet_factor must be in (0, 1]")
        super().__init__(name, rng)
        self.machine_id = machine_id
        self.start_tick = start_tick
        self.rate = rate
        self.variation = variation
        self.load_exponent = load_exponent
        self.speed_exponent = speed_exponent
        self.onset_health = onset_health
        self.quiet_factor = quiet_factor

    def apply(self, state: FactoryState, tick: int) -> None:
        # Variables:
        #   loss: Health lost this tick, drawn before any early return so the random
        #     stream stays aligned.
        #   machine: The machine being worn.
        #   replaced: The tick its bearing was last replaced, which ends this fault.
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
        if machine.condition.bearing_health > self.onset_health:
            loss *= self.quiet_factor  # before onset: wearing, not yet showing
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


class AxisDriveWear(Scenario):
    """Wears one machine's axis servo drive from `start_tick` on, while it runs.

    Changes `axis_health` and nothing else; a harder job works the drive
    harder (`load / normal load`, to `load_exponent`). The symptoms come from
    elsewhere: the following-error sensor and the controller's alarm read
    `axis_health`, and a lagging axis cuts parts off size (`defect_mark`).
    Unlike a worn bearing it adds no vibration or heat and does not slow
    the machine, so the two can be told apart.
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
        load_exponent: float = 1.0,
    ):
        # Variables:
        #   rate: Axis health lost per running tick at normal load.
        #   variation: How much the loss varies from tick to tick, as a fraction of the
        #     rate.
        #   load_exponent: How steeply a heavier load wears the drive faster.
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

    def apply(self, state: FactoryState, tick: int) -> None:
        # Variables:
        #   loss: Health lost this tick, drawn first so the random stream stays aligned.
        #   replaced: The tick the drive was last replaced, which ends this fault.
        if tick < self.start_tick:
            return
        # Drawn before the status check, as for the bearing: the stream's
        # position depends only on ticks since the start.
        loss = self.rate * self._stream.uniform(
            1.0 - self.variation, 1.0 + self.variation
        )
        machine = state.machines[self.machine_id]
        replaced = machine.axis_replaced_tick
        if replaced is not None and replaced >= self.start_tick:
            return  # the drive this fault was wearing has been replaced
        if machine.status is not MachineStatus.RUNNING:
            return
        loss *= (machine.load / NORMAL_LOAD) ** self.load_exponent
        machine.condition.axis_health = max(0.0, machine.condition.axis_health - loss)

    def ground_truth(self) -> GroundTruth:
        return GroundTruth(
            scenario=self.name,
            fault="servo_drive_wear",
            machine_id=self.machine_id,
            start_tick=self.start_tick,
        )


class HydraulicLeak(Scenario):
    """A leak in one machine's hydraulic seals from `start_tick` on, while the pump runs.

    Only a machine that has hydraulics can leak; any other is refused on the
    first tick. Changes `hydraulic_health` and nothing else. The pressure
    sensor and its low-pressure alarm read it, and a weak clamp lets parts
    shift (`defect_mark`). The pump runs whenever the machine is powered
    (running or idle), so the leak grows then too; never while it is down.
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
    ):
        # Variables:
        #   rate: Hydraulic health lost per powered tick.
        #   variation: How much the loss varies from tick to tick, as a fraction of the
        #     rate.
        if rate <= 0:
            raise ValueError("rate must be positive")
        if not 0.0 <= variation < 1.0:
            raise ValueError("variation must be in [0, 1)")
        super().__init__(name, rng)
        self.machine_id = machine_id
        self.start_tick = start_tick
        self.rate = rate
        self.variation = variation

    def apply(self, state: FactoryState, tick: int) -> None:
        # Variables:
        #   loss: Health lost this tick.
        #   replaced: The tick the seals were last replaced, which ends this fault.
        machine = state.machines[self.machine_id]
        if not machine.has_hydraulics:
            raise ValueError(f"{self.machine_id} has no hydraulic system to leak")
        if tick < self.start_tick:
            return
        loss = self.rate * self._stream.uniform(
            1.0 - self.variation, 1.0 + self.variation
        )
        repaired = machine.hydraulics_repaired_tick
        if repaired is not None and repaired >= self.start_tick:
            return  # the seals this fault was wearing have been replaced
        if machine.status is MachineStatus.DOWN:
            return
        machine.condition.hydraulic_health = max(
            0.0, machine.condition.hydraulic_health - loss
        )

    def ground_truth(self) -> GroundTruth:
        return GroundTruth(
            scenario=self.name,
            fault="hydraulic_leak",
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
        # Variables:
        #   factor: The wrong speed as a multiple of the machine's standard speed; 1 is
        #     not allowed.
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
        # Variables:
        #   batch_number: Which batch is poor; the first cannot be, because its first
        #     job is cut before this runs.
        #   added_risk: The chance of failing inspection that this batch gives each job.
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
        # Variables:
        #   duration: How many ticks the vibration sensor misreads.
        #   offset: How far the misreading is above the true value.
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
        # Variables:
        #   glitching: True while the sensor is still within its misreading window.
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
# Extra chance a worn-out axis drive would add: the axis lags its path, so
# dimensions drift. Zero for a healthy drive.
DEFECT_FROM_AXIS = 0.35
# Extra chance fully leaking hydraulics would add: the clamp holds the part
# too loosely and it shifts in the cut. Zero for sound seals.
DEFECT_FROM_HYDRAULICS = 0.30
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
    # Variables:
    #   wear: How worn the bearing is, 0 for new and 1 for failed.
    wear = 1.0 - machine.condition.bearing_health
    return (1.0 - WORN_SLOWDOWN * wear**2) * machine.speed_ratio


def defect_mark(machine) -> float:
    """What this machine adds to a job's defect risk as it finishes its part."""
    # Variables:
    #   wear: How worn the bearing is, 0 for new and 1 for failed.
    #   axis_wear: How worn the axis drive is, 0 for new and 1 for failed.
    wear = 1.0 - machine.condition.bearing_health
    axis_wear = 1.0 - machine.condition.axis_health
    return (
        DEFECT_FROM_WEAR * wear**2
        + DEFECT_FROM_SETTING * (machine.speed_ratio - 1.0) ** 2
        + DEFECT_FROM_AXIS * axis_wear**2
        + DEFECT_FROM_HYDRAULICS * (1.0 - machine.condition.hydraulic_health) ** 2
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
        # Variables:
        #   machine_ids: The machines in order along the line, each listed once.
        #   min_load: The lightest load a new job can have, from 0 to 1.
        #   max_load: The heaviest load a new job can have, from 0 to 1.
        #   time_variation: Ticks either way added to each job's time at each machine; 0
        #     for none.
        #   jobs_per_batch: Jobs cut from each material batch; 0 means no batches.
        #   _inspection_stream: A separate random stream for pass-or-fail draws, so
        #     inspections do not disturb job timing.
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
        # Variables:
        #   taken: Machines that already belong to other lines; a machine cannot be on
        #     two.
        #   line: The machine objects in line order.
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
        # Variables:
        #   chance_of_failing: Baseline plus the job's accumulated defect risk, capped
        #     at 95%.
        #   passed: Whether the random draw cleared that chance.
        #   following: The next machine, which a finished job moves into if it is free.
        #   first: The first machine, where a new job enters if it is free.
        #   job: The new job, with a random load between min_load and max_load.
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
        # Variables:
        #   batch: The batch this job is cut from; a new one opens when its last job is
        #     cut.
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
        # Variables:
        #   extra: Random ticks added or removed for this job at this machine.
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
        # Variables:
        #   mean: The average air temperature in degrees F.
        #   swing: How far the daily cycle goes above and below the mean.
        #   ticks_per_day: Ticks in one day; 1440 for one-minute ticks.
        #   warmest_tick: The tick of the first afternoon peak.
        #   drift_step: Size of the random nudge added each tick to the slow drift.
        #   drift_pull: How strongly the drift is pulled back toward zero each tick.
        #   _drift: The slow wander on top of the daily cycle.
        super().__init__(name, rng)
        self.mean, self.swing = mean, swing
        self.ticks_per_day, self.warmest_tick = ticks_per_day, warmest_tick
        self.drift_step, self.drift_pull = drift_step, drift_pull
        self._drift = 0.0

    def apply(self, state: FactoryState, tick: int) -> None:
        # Variables:
        #   time_of_day: The point in the daily cycle as an angle, with the peak at
        #     zero.
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
        # Variables:
        #   cooling: The most cooling the open door can cause.
        #   chance_per_tick: Chance that a closed door opens in any one tick.
        #   min_open: Fewest ticks it stays open.
        #   max_open: Most ticks it stays open.
        #   cool_per_tick: How fast cooling builds while the door is open.
        #   recover_per_tick: How fast cooling fades once it is closed.
        #   _closes_at: The tick the door will close.
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
        # Variables:
        #   opens: Whether the door would open this tick; drawn every tick so the stream
        #     stays aligned.
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
