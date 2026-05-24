from roamerd.contracts.errors import ErrorCode
from roamerd.contracts.exit import ExitCategory, exit_category_for_error


def test_exit_category_values_match_legacy_contract() -> None:
    assert ExitCategory.SUCCESS == 0
    assert ExitCategory.USAGE == 2
    assert ExitCategory.DEPENDENCY == 10
    assert ExitCategory.RUNTIME == 11
    assert ExitCategory.TIMEOUT == 12


def test_exit_category_for_error_canonicalizes_legacy_codes() -> None:
    assert exit_category_for_error("serve_timeout") is ExitCategory.TIMEOUT
    assert exit_category_for_error(ErrorCode.CONFIG_INVALID) is ExitCategory.USAGE
    assert exit_category_for_error("dependency.audio.aplay_missing") is ExitCategory.DEPENDENCY
    assert exit_category_for_error("unknown.new_error") is ExitCategory.RUNTIME
