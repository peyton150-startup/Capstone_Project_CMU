"""Check that CLIs provide help without running a model or using a machine.

Running the module entry point covers its public CLI contract and the
__main__ guard, not a synthetic no-op invocation of internal methods.
"""

import runpy
import sys
import warnings

import pytest


@pytest.mark.parametrize(
    "module",
    [
        "capstone.baseline",
        "capstone.evals",
        "capstone.experiment",
        "capstone.tree_reach",
        "capstone.memory_comparison",
        "capstone.memory.backfill",
        "capstone.memory.duplicate_threshold",
        "capstone.manual.index",
        "capstone.ingestion",
        "capstone.monitoring",
        "evaltools.reference_review",
        "evaltools.snap_request",
        "evaltools.full_evaluation",
        "evaltools.traced_run",
        "evaltools.run_packet",
        "evaltools.build_inventory",
        "evaltools.compare_evaluators",
    ],
)
def test_cli_module_help_is_offline_and_exits_cleanly(monkeypatch, capsys, module):
    """Every public CLI must show help before reading files or calling models."""
    monkeypatch.setattr(sys, "argv", [module, "--help"])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        with pytest.raises(SystemExit) as stopped:
            runpy.run_module(module, run_name="__main__", alter_sys=False)
    assert stopped.value.code == 0
    output = capsys.readouterr()
    assert "usage:" in output.out
