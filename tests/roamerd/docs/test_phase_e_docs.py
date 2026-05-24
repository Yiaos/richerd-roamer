from pathlib import Path


def test_phase_e_acceptance_docs_exist() -> None:
    matrix = Path("migration/phase-e-acceptance-matrix.md").read_text(encoding="utf-8")
    equivalence = Path("migration/capability-equivalence.md").read_text(encoding="utf-8")
    pi_acceptance = Path("migration/pi-acceptance-phase-e.md").read_text(encoding="utf-8")
    legacy_readme = Path("src/roamer/README.md").read_text(encoding="utf-8")

    assert "pytest tests/roamerd -q" in matrix
    assert "mypy --strict src/roamerd" in matrix
    assert "legacy CLI" in equivalence
    assert "ControlBridge" in equivalence
    assert "HARDWARE-EXCLUDED" in pi_acceptance
    assert "TRANSITIONAL" in legacy_readme


def test_phase_progress_checklists_are_tracked_artifacts() -> None:
    progress_dir = Path("migration/progress")

    for phase in ["a", "b1", "b2", "b3", "c", "d", "e"]:
        checklist = (progress_dir / f"phase-{phase}-checklist.md").read_text(
            encoding="utf-8"
        )
        assert "Verification Log" in checklist
