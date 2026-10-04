import pytest

from capstone.simulator.rng import RandomSource

VIB = "sensor.CNC-04.vibration"
TEMP = "sensor.CNC-02.temperature"


def draws(source: RandomSource, name: str, n: int = 10) -> list[float]:
    stream = source.stream(name)
    return [stream.random() for _ in range(n)]


def test_same_seed_and_name_give_same_sequence():
    assert draws(RandomSource(42), VIB) == draws(RandomSource(42), VIB)


def test_different_seeds_give_different_sequences():
    assert draws(RandomSource(42), VIB) != draws(RandomSource(43), VIB)


def test_different_names_under_same_seed_give_different_sequences():
    source = RandomSource(42)
    assert draws(source, VIB) != draws(source, TEMP)


def test_renaming_a_stream_changes_its_history():
    assert draws(RandomSource(42), VIB) != draws(RandomSource(42), "sensor.CNC-04.vib")


def test_stream_is_unaffected_by_other_streams_being_used():
    quiet = RandomSource(42)
    expected = draws(quiet, VIB)

    busy = RandomSource(42)
    draws(busy, TEMP, n=500)
    draws(busy, "events.noise", n=500)
    assert draws(busy, VIB) == expected


def test_stream_returns_the_same_object_so_position_is_preserved():
    source = RandomSource(42)
    first = source.stream(VIB)
    first.random()
    second = source.stream(VIB)
    assert second is first


def test_stream_only_advances_when_drawn_from():
    source = RandomSource(42)
    stream = source.stream(VIB)
    before = stream.getstate()
    source.stream(TEMP).random()
    source.stream(VIB)
    assert stream.getstate() == before


def test_empty_name_is_rejected():
    with pytest.raises(ValueError):
        RandomSource(42).stream("")


def test_derivation_is_pinned_so_recorded_histories_survive_refactors():
    # sha256(b"42:x") — if this changes, every recorded history changes.
    pinned = "c425cf7f0966afc26ea36c60d754a79ec59247ceadcb714e4ed76ccfc735d3a0"
    assert RandomSource(42)._derive_seed("x") == int(pinned, 16)
