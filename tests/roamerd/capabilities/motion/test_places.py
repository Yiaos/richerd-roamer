from datetime import UTC, datetime

from roamerd.capabilities.motion.places import Place, PlaceRegistry


def test_place_registry_resolves_lists_and_finds_nearest() -> None:
    registry = PlaceRegistry(
        [
            Place(name="客厅", x=1, y=2, angle=0, tolerance=300),
            Place(name="卧室", x=10, y=2, angle=None, tolerance=300),
        ]
    )

    assert registry.resolve("客厅").x == 1
    assert [place.name for place in registry.list()] == ["客厅", "卧室"]
    assert registry.nearest(9, 2).name == "卧室"


def test_place_registry_invalidates_on_map_change() -> None:
    registry = PlaceRegistry(
        [
            Place(
                name="客厅",
                x=1,
                y=2,
                map_id="old",
                map_hash="hash",
                verification_status="verified",
                verified_at=datetime.now(UTC),
            )
        ]
    )

    registry.invalidate_for_map(map_id="new", map_hash="hash")

    assert registry.resolve("客厅").verification_status == "stale"
