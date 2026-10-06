from capstone.simulator.simulator import Simulator


class ActionTools:
    """The tools that change something. Kept apart from the read-only ones.

    Looking is free: only `wait` moves the clock. So what an agent finds
    at a given tick never depends on how many times it looked first.
    """

    def __init__(self, simulator: Simulator, *, max_wait: int = 480):
        self._sim = simulator
        self.max_wait = max_wait

    def wait(self, ticks: int) -> dict:
        """Let the factory run for `ticks` ticks, then report the new time."""
        if not isinstance(ticks, int) or isinstance(ticks, bool) or not 1 <= ticks <= self.max_wait:
            raise ValueError(f"ticks must be a whole number from 1 to {self.max_wait}")
        for _ in range(ticks):
            self._sim.step()
        clock = self._sim.clock
        return {"tick": clock.tick, "time": clock.now.isoformat()}
