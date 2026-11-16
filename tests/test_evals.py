import importlib.util
import os

spec = importlib.util.spec_from_file_location(
    "run_evals", os.path.join(os.path.dirname(os.path.dirname(__file__)), "evals", "run_evals.py"))
run_evals = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_evals)


def test_eval_gate_passes_on_every_seed():
    result = run_evals.run()
    assert result["cases"] == 48 * len(run_evals.SEEDS)
    assert result["action_accuracy"] >= 0.9
    assert result["grounded_rate"] == 1.0
