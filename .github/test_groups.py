# Which test files belong to which part of the project, for the CI checks.
# Responsibility: name the groups, list their files, and fail if a file is left out.
"""One CI check per part of the project.

    python .github/test_groups.py names          the groups, as JSON
    python .github/test_groups.py files GROUP    that group's test files
    python .github/test_groups.py check          every test file is in one group

A new test file must be added to a group here. `check` fails until it is,
so a file can never be left out of every group and silently not run.
"""

import json
import sys
from pathlib import Path

TESTS = Path(__file__).resolve().parent.parent / "tests"

GROUPS: dict[str, list[str]] = {
    "Simulator": [
        "ambient",
        "bearing_degradation",
        "bearing_replacement",
        "build_line",
        "clock",
        "events",
        "failure",
        "false_alarm",
        "generator",
        "ground_truth",
        "load",
        "load_wear_coupling",
        "loading_door",
        "material_batch",
        "production_line",
        "quality",
        "rng",
        "scenarios",
        "sensors",
        "setting_reset",
        "simulator",
        "slow_when_worn",
        "state",
        "temperature_sensor",
        "thermal_lag",
        "thermometer",
        "two_lines",
        "wrong_setting",
    ],
    "Tools and provider": [
        "approval",
        "contracts",
        "factory_provider",
        "job_history",
        "observability",
        "observation_tools",
        "sensor_summary",
        "settings",
        "wait_tool",
    ],
    # Checkpoints 1-3: runtime records, inner loop, outer sequence, action path.
    "Reasoning loop": [
        "agent_artifacts",
        "agent_loop",
        "agent_investigation",
        "agent_action",
    ],
    # Checkpoint 4: looking again and judging whether the fix worked.
    "Verification": ["agent_verification"],
    # Checkpoint 5: where evidence came from, and the finished record.
    "Completed record": ["agent_provenance", "agent_completion"],
    "Memory": [
        "database_connection",
        "memory_policy",
        "memory_repository",
        "migrations",
    ],
    "Evaluation": ["evaluation", "memory_evaluation"],
    # The ungated agent and its JSON memory, kept until they are retired.
    "Older agent": ["agent", "memory"],
}


def files(group: str) -> list[str]:
    return [f"tests/test_{name}.py" for name in GROUPS[group]]


def problems() -> list[str]:
    """Test files in no group or in two, and group entries with no file."""
    on_disk = {path.name for path in TESTS.glob("test_*.py")}
    listed = [f"test_{name}.py" for names in GROUPS.values() for name in names]
    found = [f"{name} is in no CI group" for name in sorted(on_disk - set(listed))]
    found += [f"{name} does not exist" for name in sorted(set(listed) - on_disk)]
    found += [
        f"{name} is in more than one CI group"
        for name in sorted({n for n in listed if listed.count(n) > 1})
    ]
    return found


def main(argv: list[str]) -> int:
    if argv == ["names"]:
        print(json.dumps(list(GROUPS)))
        return 0
    if len(argv) == 2 and argv[0] == "files" and argv[1] in GROUPS:
        print(" ".join(files(argv[1])))
        return 0
    if argv == ["check"]:
        found = problems()
        for problem in found:
            print(problem, file=sys.stderr)
        return 1 if found else 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
