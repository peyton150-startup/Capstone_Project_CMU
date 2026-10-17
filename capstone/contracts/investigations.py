# The helpers that make run and investigation IDs.
# Responsibility: derive stable IDs. It does not run or store an agent.
from uuid import NAMESPACE_URL, UUID, uuid5


def run_id_for(run_key: str) -> UUID:
    """Caller supplies a stable, unique execution key; no simulator RNG consumed."""
    if not isinstance(run_key, str) or not run_key.strip():
        raise ValueError("run_key must be a nonempty string")
    return uuid5(NAMESPACE_URL, f"capstone/run/{run_key}")


def investigation_id_for(run_id: UUID, sequence: int) -> UUID:
    """Stable investigation identity inside a run, starting with sequence 1."""
    if type(sequence) is not int or sequence < 1:
        raise ValueError("investigation sequence must be a positive integer")
    return uuid5(run_id, f"investigation/{sequence}")

