from pathlib import Path

import pytest
from PIL import Image
from scribetex import figures


def _make_png(dir_path, w=200, h=100, name="page.png"):
    dir_path.mkdir(parents=True, exist_ok=True)
    p = dir_path / name
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
    root = tmp_path / "notes"
    # A page under the notes root is an allowed source.
    page = _make_png(root, w=200, h=100)
    res = figures.crop_to_extfiles(
        str(page), [0.0, 0.0, 0.5, 1.0], "Bio 101", "diagram", root=root,
    )
    assert res["saved"] is True
    assert res["filename"] == "diagram.png"
    out = root / "Bio-101" / "ExtFiles" / "diagram.png"
    assert out.exists()
    # Half width, full height -> 100 x 100.
    assert Image.open(out).size == (100, 100)


def test_crop_allows_scribetex_temp_page(tmp_path):
    import tempfile
    # A page under a scribetex_* render dir is also allowed, even when the
    # notes root is elsewhere.
    render_dir = Path(tempfile.mkdtemp(prefix="scribetex_"))
    page = _make_png(render_dir, w=100, h=100, name="p1.png")
    root = tmp_path / "notes"
    res = figures.crop_to_extfiles(
        str(page), [0.0, 0.0, 1.0, 1.0], "Bio", "fig", root=root,
    )
    assert res["saved"] is True
    assert (root / "Bio" / "ExtFiles" / "fig.png").exists()


def test_crop_rejects_arbitrary_path(tmp_path):
    # A page that is neither under the notes root nor a scribetex_* temp dir is
    # refused (confused-deputy guard), even though the file exists.
    outside = _make_png(tmp_path / "elsewhere", w=50, h=50)
    root = tmp_path / "notes"
    with pytest.raises(ValueError, match="page_image must be a rendered page"):
        figures.crop_to_extfiles(str(outside), [0, 0, 1, 1], "Bio", "x", root=root)


def test_crop_missing_page(tmp_path):
    with pytest.raises(FileNotFoundError, match="page image not found"):
        figures.crop_to_extfiles(str(tmp_path / "nope.png"), [0, 0, 1, 1], "Bio", "d", root=tmp_path)
