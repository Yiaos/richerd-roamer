from roamerd.contracts.errors import SCHEMA_VERSION, ErrorCode
from roamerd.contracts.result import ActionResult, attach_contract_fields, error, success


def test_success_result_shape() -> None:
    result = success({"path": "/tmp/out.wav"})

    assert result == ActionResult(ok=True, data={"path": "/tmp/out.wav"})
    assert result.model_dump(exclude_none=True) == {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "data": {"path": "/tmp/out.wav"},
    }


def test_error_result_shape_and_legacy_alias() -> None:
    result = error("driver_not_found", "missing driver")

    assert result.ok is False
    assert result.error == "driver_not_found"
    assert result.error_code == ErrorCode.DRIVER_NOT_FOUND
    assert result.model_dump(exclude_none=True)["schema_version"] == SCHEMA_VERSION


def test_attach_contract_fields_preserves_legacy_output_contract() -> None:
    payload = attach_contract_fields({"ok": True}, command="sense")

    assert payload["ok"] is True
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["command"] == "sense"
