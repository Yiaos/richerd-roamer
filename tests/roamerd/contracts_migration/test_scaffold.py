from pathlib import Path

import pytest

from roamerd.compat.legacy_cli import LegacyCliError, legacy_request
from roamerd.compat.legacy_config import migrate_legacy_config


def test_contracts_migration_scaffold_exists() -> None:
    scaffold = Path(__file__).parent

    assert scaffold.name == "contracts_migration"
    assert scaffold.exists()


def test_contracts_migration_covers_legacy_cli_core_actions() -> None:
    commands = {
        ("sense",): "sense",
        ("speak", "hello"): "speech.speak",
        ("listen",): "hearing.listen",
        ("watch",): "watch",
        ("home",): "motion.home",
        ("goto", "1", "2"): "motion.goto",
    }

    for argv, expected_action in commands.items():
        request = legacy_request(list(argv))
        assert request.op == "run"
        assert request.args["action"] == expected_action


def test_contracts_migration_rejects_unknown_legacy_cli_command() -> None:
    with pytest.raises(LegacyCliError):
        legacy_request(["legacy-only-command"])


def test_contracts_migration_reports_unmapped_config_leaves(tmp_path: Path) -> None:
    legacy_path = tmp_path / "legacy.yaml"
    legacy_path.write_text("unknown:\n  leaf: true\n", encoding="utf-8")

    _, report = migrate_legacy_config(legacy_path)

    assert report.unmapped_leaf_keys == ["unknown.leaf"]
