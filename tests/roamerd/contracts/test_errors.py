from roamerd.contracts.errors import LEGACY_ERROR_MAP, SCHEMA_VERSION, ErrorCode


def test_error_codes_cover_legacy_command_contract() -> None:
    assert SCHEMA_VERSION == "1.0"
    assert ErrorCode.DRIVER_NOT_FOUND == "driver.not_found"
    assert ErrorCode.ACTION_NOT_FOUND == "action.not_found"
    assert ErrorCode.CONFIG_INVALID == "config.invalid"
    assert LEGACY_ERROR_MAP["driver_not_found"] == ErrorCode.DRIVER_NOT_FOUND
    assert LEGACY_ERROR_MAP["serve_timeout"] == ErrorCode.SERVE_TIMEOUT

