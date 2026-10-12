"""Run the research agent on seeded scenarios and print the scores.

    python -m capstone.agent --seed 3              # one run, a trusting human approves
    python -m capstone.agent --seed 0 --runs 20    # seeds 0-19, with the summary line
    python -m capstone.agent --seed 3 --ask        # approve proposals yourself

Needs ANTHROPIC_API_KEY. Investigations are saved to memory unless --no-memory.
"""

import argparse
import sys

from capstone.agent.episode import approve_all, ask_on_console, run_episode
from capstone.agent.models import DEFAULT_MODEL, ClaudeModel
from capstone.evaluation.scoring import format_summary, summarize
from capstone.simulator.generator import FAULTS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m capstone.agent")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--fault", choices=FAULTS)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"]
    )
    parser.add_argument(
        "--ask", action="store_true", help="approve or reject proposals at the console"
    )
    parser.add_argument("--memory", default="investigations.jsonl", help="memory file")
    parser.add_argument("--no-memory", action="store_true")
    args = parser.parse_args(argv)

    if not ClaudeModel.available():
        print(
            "ANTHROPIC_API_KEY is not set; the real agent needs it (tests do not).",
            file=sys.stderr,
        )
        return 2
    memory = None
    if not args.no_memory:
        from capstone.agent.memory import InvestigationMemory

        memory = InvestigationMemory(args.memory)

    scores = []
    for seed in range(args.seed, args.seed + args.runs):
        result = run_episode(
            seed,
            ClaudeModel(args.model, effort=args.effort),
            fault=args.fault,
            approver=ask_on_console if args.ask else approve_all,
            memory=memory,
        )
        s = result.score
        print(f"seed {seed}: {result.anomaly}")
        print(
            f"  truth {s.true_fault} {s.true_machine_id or s.true_batch_id}; "
            f"agent {s.diagnosed_fault} {s.diagnosed_machine_id or s.diagnosed_batch_id}; "
            f"actions {s.actions_taken or 'none'}; resolved {s.resolved}; "
            f"{s.tool_calls} calls, {s.ticks_elapsed} ticks"
        )
        scores.append(s)
    print(format_summary(summarize(scores)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
