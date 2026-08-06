import pytest
from PIL import Image
from scribetex import figures


def _make_png(tmp_path, w=200, h=100):
    p = tmp_path / "page.png"
    Image.new("RGB", (w, h), "white").save(p)
    return p


def test_sanitize_name():
    assert figures.sanitize_name("Fig 1: Curve!") == "Fig-1-Curve"
    assert figures.sanitize_name("") == "figure"
    assert figures.sanitize_name("a/b\\c") == "a-b-c"


def test_validate_bbox_ok():
    assert figures.validate_bbox([0.1, 0.2, 0.9, 0.8]) == (0.1, 0.2, 0.9, 0.8)


@pytest.mark.parametrize("bad", [
    [0.5, 0, 0.5, 1],     # x0 == x1
    [0, 0, 1, 0],         # y0 == y1
    [-0.1, 0, 1, 1],      # x0 < 0
    [0, 0, 1.1, 1],       # x1 > 1
    [0.9, 0, 0.1, 1],     # x0 > x1
])
def test_validate_bbox_rejects(bad):
    with pytest.raises(ValueError, match="invalid bbox"):
        figures.validate_bbox(bad)


def test_crop_writes_to_extfiles(tmp_path):
    page = _make_png(tmp_path, w=200, h=100)
    root = tmp_path / "notes"
    res = figures.crop_to_extfiles(
        str(page), [0.0, 0.0, 0.5, 1.0], "Bio 101", "diagram", root=root,
    )
    assert res["saved"] is True
    assert res["filename"] == "diagram.png"
    out = root / "Bio-101" / "ExtFiles" / "diagram.png"
    assert out.exists()
    # Half width, full height -> 100 x 100.
    assert Image.open(out).size == (100, 100)


def test_crop_missing_page(tmp_path):
    with pytest.raises(FileNotFoundError, match="page image not found"):
        figures.crop_to_extfiles(str(tmp_path / "nope.png"), [0, 0, 1, 1], "Bio", "d", root=tmp_path)
