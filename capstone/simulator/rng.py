import hashlib
import random


class RandomSource:
    """The single legal source of randomness in the simulator.

    One master seed; each named stream gets its own generator seeded from
    hash(master_seed, name), so a stream's sequence depends on nothing but
    that pair. Names are part of the seed: renaming a stream changes its
    history.
    """

    def __init__(self, seed: int):
        self._seed = seed
        self._streams: dict[str, random.Random] = {}

    @property
    def seed(self) -> int:
        return self._seed

    def stream(self, name: str) -> random.Random:
        if not name:
            raise ValueError("stream name must be non-empty")
        if name not in self._streams:
            self._streams[name] = random.Random(self._derive_seed(name))
        return self._streams[name]

    def _derive_seed(self, name: str) -> int:
        # sha256, not hash(): Python salts str hashing per process, which
        # would make every run a different world.
        digest = hashlib.sha256(f"{self._seed}:{name}".encode()).digest()
        return int.from_bytes(digest, "big")
