from capstone.simulator.simulator import Simulator


class ObservationTools:
    """The agent's only view of the factory. Read-only.

    Every answer is built from scratch, field by field, out of plain
    values. Anything not named here stays hidden, including whatever is
    added to the simulator later. Nothing here advances time.
    """

    def __init__(self, simulator: Simulator):
        self._sim = simulator

    def get_time(self) -> dict:
        clock = self._sim.clock
        return {"tick": clock.tick, "time": clock.now.isoformat()}

    def list_machines(self) -> list[dict]:
        return [
            {"machine_id": machine.id, "status": machine.status.value}
            for machine in self._sim.state.machines.values()
        ]

    def get_readings(self, machine_id: str, sensor: str, from_tick: int, to_tick: int) -> list[dict]:
        self._check(machine_id, from_tick, to_tick)
        return [
            {"tick": r.tick, "machine_id": r.machine_id, "sensor": r.sensor, "value": r.value, "unit": r.unit}
            for r in self._sim.readings
            if r.machine_id == machine_id and r.sensor == sensor and from_tick <= r.tick <= to_tick
        ]

    def get_events(self, from_tick: int, to_tick: int, machine_id: str | None = None) -> list[dict]:
        self._check(machine_id, from_tick, to_tick)
        return [
            {"tick": e.tick, "machine_id": e.machine_id, "kind": e.kind, "message": e.message}
            for e in self._sim.event_log.events
            if from_tick <= e.tick <= to_tick and machine_id in (None, e.machine_id)
        ]

    def _check(self, machine_id: str | None, from_tick: int, to_tick: int) -> None:
        if machine_id is not None and machine_id not in self._sim.state.machines:
            raise ValueError(f"unknown machine {machine_id}")
        if from_tick > to_tick:
            raise ValueError("from_tick must not be after to_tick")
