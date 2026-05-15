import tomllib
from pathlib import Path

FORMAT_COMMAND = (
    "ruff format --check src/roamerd tests/roamerd sitecustomize.py "
    "readline.py ros2_ws/src/roamer_ros/roamer_ros"
)
LINT_COMMAND = (
    "ruff check src/roamerd tests/roamerd sitecustomize.py "
    "readline.py ros2_ws/src/roamer_ros/roamer_ros"
)


def test_dev_extra_contains_roamerd_gate_tools() -> None:
    project = tomllib.loads(Path("pyproject.toml").read_text())

    dev_deps = project["project"]["optional-dependencies"]["dev"]
    normalized = {dependency.split(">=", 1)[0] for dependency in dev_deps}
    assert {"pytest", "ruff", "mypy", "websockets"} <= normalized


def test_github_workflow_runs_roamerd_pr_gates() -> None:
    workflow = Path(".github/workflows/roamerd.yml").read_text()

    assert "uses: actions/checkout@v6" in workflow
    assert "uses: actions/setup-python@v6" in workflow
    assert 'python-version: "3.13"' in workflow
    assert 'python -m pytest -m "not hardware" -q' in workflow
    assert "mypy --strict" in workflow
    assert FORMAT_COMMAND in workflow
    assert LINT_COMMAND in workflow
    assert "bash -n scripts/roamerd-pi-preflight.sh" in workflow
    assert "bash -n scripts/roamerd-pi-collect-phase-e-facts.sh" in workflow
    assert "bash -n scripts/roamerd-pi-phase-e-acceptance.sh" in workflow
    assert "bash -n scripts/roamerd-pi-ubuntu24-bootstrap.sh" in workflow
