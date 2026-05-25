import subprocess
import sys


def test_python_module_help_outputs_usage() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "roamerd", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "usage:" in result.stdout
