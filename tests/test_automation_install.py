import plistlib
from pathlib import Path
import pytest
from automation import install, config


def _cfg(tmp_path):
    return config.load_config(env={"SCRIBETEX_INBOX": str(tmp_path)}, toml_path=None)


def test_render_watch_plist_valid():
    xml = install.render_plist(
        "com.scribetex.watch",
        ["/usr/bin/python3", "-m", "automation.ingest", "--once"],
        watch_paths=["/inbox"], log_file="/tmp/x.log",
    )
    data = plistlib.loads(xml.encode())
    assert data["Label"] == "com.scribetex.watch"
    assert data["WatchPaths"] == ["/inbox"]
    assert data["ProgramArguments"][-1] == "--once"
    assert "StartInterval" not in data


def test_render_sweep_plist_valid():
    xml = install.render_plist(
        "com.scribetex.sweep",
        ["/usr/bin/python3", "-m", "automation.ingest", "--sweep"],
        start_interval=600, log_file="/tmp/x.log",
    )
    data = plistlib.loads(xml.encode())
    assert data["StartInterval"] == 600
    assert "WatchPaths" not in data


def test_render_requires_exactly_one_trigger():
    with pytest.raises(ValueError):
        install.render_plist("l", ["x"], log_file="/t")  # neither
    with pytest.raises(ValueError):
        install.render_plist("l", ["x"], watch_paths=["/a"],
                             start_interval=1, log_file="/t")  # both


def test_build_plists_targets_and_content(tmp_path):
    cfg = _cfg(tmp_path)
    plists = install.build_plists(cfg, "/usr/bin/python3", "/repo")
    labels = {p.name for p in plists}
    assert "com.scribetex.watch.plist" in labels
    assert "com.scribetex.sweep.plist" in labels
    watch_xml = next(v for k, v in plists.items() if "watch" in k.name)
    assert str(tmp_path) in watch_xml  # inbox in WatchPaths
    assert "/repo" in watch_xml        # PYTHONPATH/WorkingDirectory


def test_build_plists_sets_path_env(tmp_path):
    cfg = _cfg(tmp_path)
    plists = install.build_plists(cfg, "/usr/bin/python3", "/repo")
    for xml in plists.values():
        data = plistlib.loads(xml.encode())
        env = data["EnvironmentVariables"]
        assert "PYTHONPATH" in env
        assert "PATH" in env
        assert "/opt/homebrew/bin" in env["PATH"]


def test_preflight_flags_missing_claude(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path)
    tmp_path.mkdir(exist_ok=True)
    monkeypatch.setattr(install.shutil, "which", lambda x, path=None: None)
    problems = install.preflight(cfg, "claude", str(tmp_path))
    assert any("claude" in p.lower() for p in problems)
