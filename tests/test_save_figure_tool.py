from PIL import Image
from scribetex import server


def _png(tmp_path):
    p = tmp_path / "p1.png"
    Image.new("RGB", (300, 200), "white").save(p)
    return p


def test_save_figure_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRIBETEX_NOTES_ROOT", str(tmp_path))
    page = _png(tmp_path)
    res = server._save_figure("Bio 101", str(page), [0.0, 0.0, 1.0, 0.5], "curve")
    assert res["saved"] is True
    assert res["filename"] == "curve.png"
    assert "includegraphics" in res["include"]
    assert "curve" in res["include"]
    assert (tmp_path / "Bio-101" / "ExtFiles" / "curve.png").exists()


def test_save_figure_bad_bbox_returns_error(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRIBETEX_NOTES_ROOT", str(tmp_path))
    page = _png(tmp_path)
    res = server._save_figure("Bio 101", str(page), [0, 0, 0, 1], "curve")
    assert res["saved"] is False
    assert "invalid bbox" in res["error"]


def test_save_figure_missing_page_returns_error(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRIBETEX_NOTES_ROOT", str(tmp_path))
    res = server._save_figure("Bio 101", str(tmp_path / "nope.png"), [0, 0, 1, 1], "c")
    assert res["saved"] is False
    assert "page image not found" in res["error"]
