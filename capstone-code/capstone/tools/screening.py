# The line screening: every machine's recent running readings against a saved healthy line.
# Responsibility: turn observable readings into numbers, never into labels or causes.
"""Line screening against a saved "before" file.

The "before" file (`healthy_reference.json`, next to this module) holds each
machine's normal running range per sensor, recorded from a fault-free run of
the line. `screen_line` compares every machine's latest running readings with
it and returns plain numbers: two scores and the window behind them. It never
says "abnormal", names no cause, and reads nothing the agent could not fetch.

The file is the one place the screening's settings live (the seed and length
of the healthy run, the running threshold, window sizes, warm-up stages).
`write_reference` makes it; everything else reads it, so a setting cannot be
copied somewhere and drift. Regenerate it whenever the sensor model changes,
and record a new one from a confirmed healthy period before using real data:

    uv run python -m capstone.tools.screening
"""

import json
import statistics
from functools import lru_cache
from pathlib import Path

REFERENCE_PATH = Path(__file__).with_name("healthy_reference.json")

# What the generator records. Only `write_reference` reads these; the screening
# reads the copy saved in the file.
GENERATOR_SETTINGS = {
    "source": "separate baseline run of the simulated standard line, normal operation",
    "seed": 1,
    "machines": 8,
    # Two days, so the daily swing in factory air temperature and several
    # material batches are both inside the healthy range.
    "ticks": 2880,
    # A reading counts as "running" when the same machine's load reading at
    # the same tick is above this (idle load is near 0, cutting about 30+).
    "running_load": 15.0,
    # How many of a machine's latest running readings are scored, and the
    # fewest that still give a score.
    "recent_readings": 60,
    "min_recent": 20,
    # Warm-up stages, by how many running readings the machine had before a
    # reading: [0, 50) "start", [50, 150) "warming", 150 and over "steady".
    "warmup_boundaries": [50, 150],
    # Only heat has a warm-up: a machine that has just started cutting runs
    # cold. Every other sensor has one range over all running readings (its
    # stage is "running"), because splitting it would leave a stage holding a
    # single material batch, far narrower than normal.
    "warmup_sensors": ["temperature"],
}
STAGES = ("start", "warming", "steady")
NO_WARMUP = "running"
SENSORS = (
    "vibration",
    "temperature",
    "load",
    "power",
    "following_error",
    "hydraulic_pressure",
)
DECIMALS = 6


def stage_of(sensor: str, position: int, settings: dict) -> str:
    """The warm-up stage of a machine's running reading number `position` (0 = first)."""
    # Variables:
    #   sensor: Which sensor the reading came from; only warm-up sensors have stages.
    #   position: How many running readings the machine had before this one.
    #   settings: The screening settings; their warm-up boundaries say where
    #     "start" and "warming" end, and only their warm-up sensors have stages.
    if sensor not in settings["warmup_sensors"]:
        return NO_WARMUP
    return STAGES[sum(position >= edge for edge in settings["warmup_boundaries"])]


def running_series(
    by_sensor: dict[str, list[tuple[int, float]]], running_load: float
) -> tuple[dict[int, int], dict[str, list[tuple[int, float]]]]:
    """Which ticks the machine was cutting, and each sensor's readings at those ticks.

    Only readings at ticks where the machine's own load shows it cutting are
    kept. With no load readings nothing counts as running.
    """
    # Variables:
    #   by_sensor: One machine's readings, sensor -> (tick, value) in tick order.
    #   running_load: The load above which a tick counts as cutting, from the file.
    #   running_ticks: The ticks, in order, at which the machine was cutting.
    #   position: For each running tick, how many running ticks came before it;
    #     that count decides the warm-up stage.
    running_ticks = [t for t, v in by_sensor.get("load", []) if v > running_load]
    position = {tick: index for index, tick in enumerate(running_ticks)}
    return position, {
        sensor: [(tick, value) for tick, value in rows if tick in position]
        for sensor, rows in by_sensor.items()
    }


def summarize(values: list[float]) -> dict:
    """Median, MAD-based spread, mean, standard deviation and count of some readings."""
    # Variables:
    #   median: The middle reading; resists the odd spike.
    #   spread: The median absolute deviation scaled by 1.4826, so it matches a
    #     standard deviation when readings are normally spread.
    median = statistics.median(values)
    spread = statistics.median(abs(v - median) for v in values) * 1.4826
    return {
        "median": round(median, DECIMALS),
        "spread": round(spread, DECIMALS),
        "mean": round(statistics.fmean(values), DECIMALS),
        "sd": round(statistics.pstdev(values), DECIMALS),
        "count": len(values),
    }


def build_ranges(
    readings: dict[str, dict[str, list[tuple[int, float]]]], settings: dict
) -> dict:
    """Each machine's running range per sensor and warm-up stage, from healthy readings."""
    # Variables:
    #   readings: The healthy run's readings, machine -> sensor -> (tick, value).
    #   settings: The screening settings, for the running threshold and stages.
    #   position: For each running tick, how many running ticks came before it.
    #   grouped: One sensor's running readings sorted into their warm-up stage.
    #   stages: That sensor's range per stage; a stage with fewer than two
    #     readings is left out.
    #   ranges: The result, machine -> sensor -> stage -> range.
    ranges: dict = {}
    for machine_id, by_sensor in sorted(readings.items()):
        position, series = running_series(by_sensor, settings["running_load"])
        for sensor, rows in sorted(series.items()):
            grouped: dict[str, list[float]] = {}
            for tick, value in rows:
                stage = stage_of(sensor, position[tick], settings)
                grouped.setdefault(stage, []).append(value)
            stages = {s: summarize(v) for s, v in grouped.items() if len(v) >= 2}
            if stages:
                ranges.setdefault(machine_id, {})[sensor] = stages
    return ranges


def machine_readings(sim) -> dict[str, dict[str, list[tuple[int, float]]]]:
    """Every machine sensor reading so far, machine -> sensor -> (tick, value), in tick order."""
    # Variables:
    #   sim: The simulator whose public readings are grouped; nothing hidden is read.
    grouped: dict[str, dict[str, list[tuple[int, float]]]] = {}
    for reading in sim.readings:
        if reading.machine_id is not None:
            grouped.setdefault(reading.machine_id, {}).setdefault(
                reading.sensor, []
            ).append((reading.tick, reading.value))
    return grouped


def make_reference(settings: dict = GENERATOR_SETTINGS) -> dict:
    """Run the line with no fault and build the "before" file's contents."""
    # Variables:
    #   settings: What to record, saved into the file so the screening reads them
    #     from there and nowhere else.
    #   sim: A standard line with no fault added, stepped `ticks` times.
    from capstone.simulator.generator import JOBS_PER_BATCH
    from capstone.simulator.line import build_line

    sim = build_line(
        settings["seed"], machines=settings["machines"], jobs_per_batch=JOBS_PER_BATCH
    )
    for _ in range(settings["ticks"]):
        sim.step()
    return {
        "settings": settings,
        "ranges": build_ranges(machine_readings(sim), settings),
    }


def write_reference(path: Path = REFERENCE_PATH) -> None:
    """Regenerate the "before" file. Deterministic: the same code writes the same file."""
    # Variables:
    #   path: Where to write; the file next to this module unless a test says otherwise.
    #   text: The file's contents with keys sorted, written with plain line
    #     endings so the same run gives the same bytes on every operating system.
    text = json.dumps(make_reference(), indent=1, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    load_reference.cache_clear()


@lru_cache(maxsize=4)
def load_reference(path: Path = REFERENCE_PATH) -> dict:
    """The saved "before" file, read once."""
    # Variables:
    #   path: Which file to read; the one next to this module unless a test says otherwise.
    return json.loads(path.read_text(encoding="utf-8"))


def score(values: list[tuple[float, dict]]) -> tuple[float, float]:
    """Two scores for readings, each against its own warm-up stage's healthy range.

    robust: the median of (reading - healthy median) / healthy spread.
    plain: the mean of (reading - healthy mean) / healthy standard deviation.
    A spread of 0 is treated as a very small number, so any change shows.
    """
    # Variables:
    #   values: Each reading paired with the healthy range of its own stage.
    #   robust: How far the readings sit from healthy, by medians; one spike
    #     barely moves it.
    #   plain: The same by means; a few large readings move it more.
    robust = statistics.median(
        (v - ref["median"]) / (ref["spread"] or 1e-9) for v, ref in values
    )
    plain = statistics.fmean(
        (v - ref["mean"]) / (ref["sd"] or 1e-9) for v, ref in values
    )
    return round(robust, 2), round(plain, 2)


def screen_machine(
    machine_id: str,
    by_sensor: dict[str, list[tuple[int, float]]],
    reference: dict,
) -> list[dict]:
    """One row per sensor the machine has: coverage, window and two scores, or why none."""
    # Variables:
    #   by_sensor: The machine's observable readings so far, sensor -> (tick, value).
    #   reference: The "before" file: its settings and every machine's ranges.
    #   settings: The screening settings saved in the "before" file.
    #   position: For each running tick, how many running ticks came before it;
    #     empty means the machine has not cut yet.
    #   series: The machine's running readings per sensor, in tick order.
    #   ranges: The machine's healthy ranges per sensor and stage; empty if the
    #     file has none for it.
    #   stages: One sensor's healthy range per warm-up stage.
    #   recent: The latest running readings that have a healthy range to compare
    #     to, each with its stage.
    #   row: The answer for one sensor. Its status is "scored" or why not
    #     (not_running_yet, too_few_running_readings, no_reference): a coverage
    #     fact, never a verdict on health.
    settings = reference["settings"]
    position, series = running_series(by_sensor, settings["running_load"])
    ranges = reference["ranges"].get(machine_id, {})
    rows = []
    for sensor in SENSORS:
        if sensor not in by_sensor:
            continue
        row = {
            "machine_id": machine_id,
            "sensor": sensor,
            "running_readings": len(position),
            "reference": settings["source"],
        }
        rows.append(row)
        if not position:
            row["status"] = "not_running_yet"
            continue
        stages = ranges.get(sensor, {})
        if not stages:
            row["status"] = "no_reference"
            continue
        recent = []
        for tick, value in series[sensor]:
            stage = stage_of(sensor, position[tick], settings)
            if stage in stages:
                recent.append((tick, value, stage))
        recent = recent[-settings["recent_readings"] :]
        if len(recent) < settings["min_recent"]:
            row["status"] = "too_few_running_readings"
            row["window_readings"] = len(recent)
            continue
        robust, plain = score([(v, stages[s]) for _, v, s in recent])
        row.update(
            status="scored",
            warmup_stage=recent[-1][2],
            window_readings=len(recent),
            window_from_tick=recent[0][0],
            window_to_tick=recent[-1][0],
            window_median=round(statistics.median(v for _, v, _ in recent), 3),
            reference_median=stages[recent[-1][2]]["median"],
            robust_score=robust,
            plain_score=plain,
        )
    return rows


def screen_line(
    machine_ids: list[str],
    readings: dict[str, dict[str, list[tuple[int, float]]]],
    reference: dict | None = None,
) -> list[dict]:
    """Screen every machine on the line, in line order."""
    # Variables:
    #   machine_ids: The line's machines in order; a machine with no readings yet
    #     still gets rows only once it has some.
    #   readings: Every observable machine reading so far, machine -> sensor ->
    #     (tick, value).
    #   reference: The "before" file; None reads the saved one.
    reference = reference or load_reference()
    rows = []
    for machine_id in machine_ids:
        rows += screen_machine(machine_id, readings.get(machine_id, {}), reference)
    return rows


# What a machine's entry says when its sensor feed is down (set by the hazard
# provider, never by the screening itself).
FEED_UNAVAILABLE = "feed_unavailable"


def compact(rows: list[dict], reference: dict | None = None) -> dict:
    """The screening as the agent receives it: short enough to be shown whole.

    A prompt shows only the start of one piece of evidence
    (`model_policy.MAX_EVIDENCE_CHARS`), and the full rows run far past it, so
    most machines were never seen. Here each
    machine maps each sensor to [robust_score, plain_score] (temperature adds
    its warm-up stage), or to why it has no score. A machine whose sensors all
    share one such reason maps straight to it. The window details are left
    out: the readings themselves are one get_sensor_summary away.
    """
    # Variables:
    #   rows: The full per-sensor rows from `screen_line`, in line order.
    #   reference: The "before" file, for the one line naming where the
    #     baseline came from; None reads the saved one.
    #   machines: The answer, machine -> sensor -> scores or reason, in line order.
    #   entry: One sensor's scores, with its warm-up stage when it has one, or
    #     the reason it has none.
    #   reasons: The set of values in one machine's entry, used to fold a
    #     machine with a single reason for every sensor into that one word.
    reference = reference or load_reference()
    machines: dict[str, dict] = {}
    for row in rows:
        if row["status"] == "scored":
            entry = [row["robust_score"], row["plain_score"]]
            if row["warmup_stage"] != NO_WARMUP:
                entry.append(row["warmup_stage"])
        else:
            entry = row["status"]
        machines.setdefault(row["machine_id"], {})[row["sensor"]] = entry
    for machine_id, sensors in machines.items():
        reasons = set(map(str, sensors.values()))
        if len(reasons) == 1 and all(isinstance(v, str) for v in sensors.values()):
            machines[machine_id] = reasons.pop()
    return {"reference": reference["settings"]["source"], "machines": machines}


if __name__ == "__main__":
    write_reference()
    print(f"wrote {REFERENCE_PATH}")
