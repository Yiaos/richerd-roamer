from pathlib import Path


def test_roamerd_motion_does_not_import_valetudo_http() -> None:
    forbidden = ("ValetudoMotionDriver", "/api/v2/robot", "urllib_request")
    matches = []
    for path in Path("src/roamerd").rglob("*.py"):
        text = path.read_text()
        for pattern in forbidden:
            if pattern in text:
                matches.append((path, pattern))

    assert matches == []
