import json
from automation import appcli


def test_known_courses_lists_folders(tmp_path, monkeypatch):
    # Point the scribetex NOTES root at a temp dir with two course folders.
    monkeypatch.setenv("SCRIBETEX_NOTES_ROOT", str(tmp_path))
    (tmp_path / "Organic Chemistry").mkdir()
    (tmp_path / "Organic Chemistry" / "main.tex").touch()
    (tmp_path / "BIOS 20200").mkdir()
    (tmp_path / "BIOS 20200" / "main.tex").touch()
    (tmp_path / "not-a-course.txt").write_text("x")
    courses = set(appcli._known_courses())
    assert "Organic Chemistry" in courses
    assert "BIOS 20200" in courses


def test_known_courses_subcommand_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SCRIBETEX_NOTES_ROOT", str(tmp_path))
    (tmp_path / "Physics 101").mkdir()
    (tmp_path / "Physics 101" / "main.tex").touch()
    rc = appcli.main(["known-courses"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert "Physics 101" in out["courses"]
