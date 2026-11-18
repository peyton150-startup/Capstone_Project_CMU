"""Haas opt-in CLI refuses unsafe preflight before touching a CNC."""

import pytest

from capstone.ingestion.__main__ import main
from tests.test_channel_map import probe
from tests.test_haas_profile import profile


def test_guarded_cli_qualifies_one_device_and_saves_probe(tmp_path, monkeypatch):
    configuration = tmp_path / "approved-profile.json"
    configuration.write_text(
        profile(machine_identity="VF2").model_dump_json(),
        encoding="utf-8",
    )
    observed = []

    def fake_get(settings, url):
        observed.append(url)
        return probe()

    monkeypatch.setattr("capstone.ingestion.__main__.haas_get", fake_get)
    target = tmp_path / "machine-probe.xml"
    assert main([
        "--haas-profile", str(configuration),
        "--save-probe", str(target),
    ]) == 0
    assert observed == ["http://192.168.10.4:8082/VF-4/probe"]
    assert "MTConnectDevices" in target.read_text(encoding="utf-8")


def test_guarded_cli_refuses_bad_device_or_rate_without_network(tmp_path, monkeypatch):
    configuration = tmp_path / "approved-profile.json"
    configuration.write_text(profile().model_dump_json(), encoding="utf-8")

    def fake_get(settings, url):
        pytest.fail("must not connect to controller")

    monkeypatch.setattr("capstone.ingestion.__main__.haas_get", fake_get)
    with pytest.raises(SystemExit):
        main([
            "--haas-profile", str(configuration),
            "--device", "different-device",
            "--save-probe", str(tmp_path / "probe.xml"),
        ])
    with pytest.raises(SystemExit):
        main([
            "--haas-profile", str(configuration),
            "--interval", "0.1",
            "--save-probe", str(tmp_path / "probe.xml"),
        ])
    with pytest.raises(SystemExit):
        main(["--haas-profile", str(configuration)])
