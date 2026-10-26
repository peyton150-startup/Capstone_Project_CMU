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
        "maintenance_history",
        "material_batch",
        "power_sensor",
        "production_line",
        "quality",
        "rng",
        "scenarios",
        "sensors",
        "servo_drive",
        "setting_reset",
        "simulator",
        "simulator_challenge",
        "simulator_disturbances",
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
        "hazards",
        "chat_client",
        "request_deadline",
        "console",
        "difficulty_tool_compatibility",
        "embeddings",
        "job_history",
        "observability",
        "observation_tools",
        "sensor_summary",
        "settings",
        "env_example",
        "typesafe_client",
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
    # Checkpoint 6: the reflection candidate and the memory gate.
    "Reflection": ["memory_reflection", "learning"],
    # Checkpoint 7: recalling memories, and the guards on what a memory may prove.
    "Recall": ["recall_tool", "manual"],
    # Checkpoint 8b-2: the model-backed policy, its prompts and answer types.
    "Model policy": ["model_policy", "tree_of_thought"],
    # Checkpoint 8c: each model measured alone, from real episodes.
    "Benchmark": ["benchmark"],
    "Memory": [
        "database_connection",
        "duplicate_threshold",
        "memory_policy",
        "memory_recall",
        "memory_repository",
        "memory_semantic",
        "migrations",
    ],
    "Evaluation": [
        "evaluation",
        "memory_evaluation",
        "scoring_integrity",
        "auto_label",
        "fault_packs",
    ],
    # Many episodes: the harness, hand labels and the known-answer cases.
    "Experiments": ["experiment", "known_answers", "baseline", "memory_comparison"],
    # The runner: one seeded episode from fault to score, end to end.
    "Episode": ["episode"],
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
