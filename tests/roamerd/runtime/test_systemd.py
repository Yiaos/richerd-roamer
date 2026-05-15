from pathlib import Path


def test_roamerd_systemd_service_runs_new_runtime() -> None:
    service = Path("systemd/roamerd.service").read_text()

    assert "Description=Roamer body runtime daemon" in service
    assert "WorkingDirectory=/home/richerd/worksp/richerd-roamer" in service
    assert "python -m roamerd --config config/roamerd.yaml serve" in service
    assert "roamer serve" not in service
    assert "RuntimeDirectory=roamer" in service
    assert "RuntimeDirectoryMode=0700" in service
    assert "UMask=0077" in service
    assert "Restart=on-failure" in service
