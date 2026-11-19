"""Browser access roles: which token unlocks what, plus a setup CLI.

The FastAPI service accepts four static bearer tokens, one per role. This
module names them in one place, tells a caller which roles a token holds
(never the token itself), and gives operators a command to generate and check
them:

    uv run python -m capstone.api.access generate   # print four new tokens
    uv run python -m capstone.api.access check      # validate the current env

`check` reports variable names and problems only; it never prints a value.
"""

from __future__ import annotations

import argparse
import hmac
import os
import secrets
import sys
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from capstone.api.config import UiConfig

Role = Literal["viewer", "operator", "reviewer", "evaluator"]

# One entry per role, in the order a person sets them up.
ROLE_VARIABLES: dict[Role, str] = {
    "viewer": "CAPSTONE_UI_TOKEN",
    "operator": "CAPSTONE_UI_RUN_TOKEN",
    "reviewer": "CAPSTONE_UI_REVIEW_TOKEN",
    "evaluator": "CAPSTONE_UI_EVALUATOR_TOKEN",
}
# What each role is for, shown by the CLI and mirrored in the browser dialog.
ROLE_PURPOSE: dict[Role, str] = {
    "viewer": "read pages",
    "operator": "start simulator runs",
    "reviewer": "approve or reject proposed actions",
    "evaluator": "see evaluation records and scorecards",
}
MIN_TOKEN_LENGTH = 24
RUNS_VARIABLE = "CAPSTONE_UI_SIM_RUNS"


def generate_tokens() -> dict[str, str]:
    """Return four new, distinct, URL-safe tokens keyed by variable name."""
    # Variables:
    #   tokens: The new value for each role's variable; 32 random bytes each
    #     (43 characters), well over the 24-character minimum.
    tokens: dict[str, str] = {}
    while len(set(tokens.values())) < len(ROLE_VARIABLES):
        tokens = {name: secrets.token_urlsafe(32) for name in ROLE_VARIABLES.values()}
    return tokens


def env_block(tokens: Mapping[str, str]) -> str:
    """Format tokens as `.env` / dashboard lines, with runs switched on."""
    # Variables:
    #   lines: One `NAME=value` line per role, then the runs switch, so the
    #     block can be pasted into Render, Northflank or a local `.env`.
    lines = [f"{name}={tokens[name]}" for name in ROLE_VARIABLES.values()]
    lines.append(f"{RUNS_VARIABLE}=1")
    return "\n".join(lines) + "\n"


def roles_for(supplied: str, cfg: UiConfig) -> list[Role]:
    """Name the roles a bearer token holds, comparing in constant time."""
    # Variables:
    #   supplied: The token the browser sent, without the `Bearer ` prefix.
    #   configured: Each role's server-side token; unset roles never match.
    if not supplied:
        return []
    configured: dict[Role, str | None] = {
        "viewer": cfg.token,
        "operator": cfg.run_token,
        "reviewer": cfg.review_token,
        "evaluator": cfg.evaluator_token,
    }
    return [
        role
        for role, expected in configured.items()
        if expected and hmac.compare_digest(supplied, expected)
    ]


def check_environment(env: Mapping[str, str]) -> list[str]:
    """List problems with the access variables in `env`, by name only."""
    # Variables:
    #   values: Each role variable's trimmed value; empty when unset.
    #   runs: Whether managed runs are switched on, which makes the operator
    #     and reviewer tokens mandatory.
    #   seen: First variable holding each value, to report duplicates by name.
    values = {name: (env.get(name) or "").strip() for name in ROLE_VARIABLES.values()}
    runs = env.get(RUNS_VARIABLE) == "1"
    required = [ROLE_VARIABLES["viewer"]]
    if runs:
        required += [ROLE_VARIABLES["operator"], ROLE_VARIABLES["reviewer"]]
    problems = [f"{name} is not set" for name in required if not values[name]]
    for name, value in values.items():
        if value and len(value) < MIN_TOKEN_LENGTH:
            problems.append(f"{name} is shorter than {MIN_TOKEN_LENGTH} characters")
    seen: dict[str, str] = {}
    for name, value in values.items():
        if value and value in seen:
            problems.append(f"{name} is the same as {seen[value]}; each must differ")
        elif value:
            seen[value] = name
    if not runs and (
        values[ROLE_VARIABLES["operator"]] or values[ROLE_VARIABLES["reviewer"]]
    ):
        problems.append(f"{RUNS_VARIABLE}=1 is not set, so runs stay off")
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    """Run `generate` or `check`; return the process exit code."""
    # Variables:
    #   command: Which subcommand the operator asked for.
    #   problems: Names-only findings from `check`; any makes the exit code 1.
    parser = argparse.ArgumentParser(prog="python -m capstone.api.access")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("generate", help="print four new tokens as env lines")
    sub.add_parser("check", help="validate the access variables in this env")
    command = parser.parse_args(argv).command
    if command == "generate":
        sys.stdout.write(env_block(generate_tokens()))
        sys.stderr.write(
            "Set these on the API service (Render or local .env), then restart it.\n"
            "Paste each token into its own box in the UI's Access dialog.\n"
        )
        return 0
    problems = check_environment(os.environ)
    for role, name in ROLE_VARIABLES.items():
        state = "set" if (os.environ.get(name) or "").strip() else "unset"
        print(f"{name:<29} {state:<6} {role}: {ROLE_PURPOSE[role]}")
    for problem in problems:
        print("problem: " + problem)
    print("ok" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
