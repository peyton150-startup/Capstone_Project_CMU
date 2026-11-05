# Keeps real-machine telemetry out of git checkouts, so it cannot be committed by accident.
# Responsibility: find the git checkout a file would be written into, if any.
"""Refuse to write shop telemetry inside a git checkout.

This repository is public. Collected telemetry, the machine's /probe file and
alerts can name a shop's machines, programs and timings, so the command lines
refuse an output path inside any git checkout unless --allow-inside-repo is
given (for synthetic fixtures only). Write real data to a folder outside the
repository instead.
"""

from pathlib import Path

ALLOW_FLAG = "--allow-inside-repo"
ALLOW_HELP = (
    "allow an output path inside a git checkout (synthetic fixtures only; "
    "never real shop data)"
)


def git_checkout_containing(path: Path) -> Path | None:
    """The folder of the git checkout that path is inside, or None."""
    # Variables:
    #   path: The file about to be written; it need not exist yet.
    #   folder: Each folder above the file, nearest first. A `.git` entry (a
    #     folder in a normal checkout, a file in a worktree) marks a checkout.
    for folder in path.resolve().parents:
        if (folder / ".git").exists():
            return folder
    return None


def refusal(path: Path, option: str) -> str | None:
    """The error message when path is inside a git checkout, else None."""
    # Variables:
    #   option: The command-line option that named the path, for the message.
    #   checkout: The checkout the path is inside, if any.
    checkout = git_checkout_containing(path)
    if checkout is None:
        return None
    return (
        f"{option} {path} is inside the git checkout {checkout}; write real "
        f"telemetry outside the repository, or pass {ALLOW_FLAG} for "
        "synthetic fixtures only"
    )
