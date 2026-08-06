import pytest
from pathlib import Path
from scribetex.sources.base import get_source
from scribetex.sources.file_source import FileSource


def _make_pdf(path: Path, pages: int) -> None:
    import fitz
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page()
    doc.save(str(path))
    doc.close()


def test_registered_file_source():
    assert isinstance(get_source("file"), FileSource)


def test_goodnotes_alias_is_file_source():
    assert isinstance(get_source("goodnotes"), FileSource)


def test_heic_image_passthrough(tmp_path):
    img = tmp_path / "note.heic"
    img.write_bytes(b"\x00\x00\x00\x18ftypheic")  # stub; path handling under test
    out = FileSource().fetch_pages(str(img))
    assert out == [img]


def test_pdf_renders_one_png_per_page(tmp_path):
    pdf = tmp_path / "note.pdf"
    _make_pdf(pdf, 3)
    pngs = FileSource().fetch_pages(str(pdf))
    assert len(pngs) == 3
    assert all(p.suffix == ".png" and p.exists() for p in pngs)


def test_single_image_passthrough(tmp_path):
    img = tmp_path / "note.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")  # header only; path handling under test
    out = FileSource().fetch_pages(str(img))
    assert out == [img]


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        FileSource().fetch_pages(str(tmp_path / "nope.pdf"))


def test_unsupported_extension_raises(tmp_path):
    bad = tmp_path / "note.txt"
    bad.write_text("x")
    with pytest.raises(ValueError):
        FileSource().fetch_pages(str(bad))


def test_onenote_source_not_implemented():
    from scribetex.sources.onenote_source import OneNoteSource
    with pytest.raises(NotImplementedError):
        OneNoteSource().fetch_pages("anything")
