import pytest
from scribetex.sources.file_source import FileSource


def test_empty_ref_names_the_field():
    with pytest.raises(ValueError, match=r"no note path provided: pass ref="):
        FileSource().fetch_pages("")


def test_blank_ref_names_the_field():
    with pytest.raises(ValueError, match=r"no note path provided"):
        FileSource().fetch_pages("   ")


def test_missing_file_message(tmp_path):
    missing = tmp_path / "nope.pdf"
    with pytest.raises(FileNotFoundError, match=r"file not found:.*nope\.pdf"):
        FileSource().fetch_pages(str(missing))


def test_unsupported_extension_lists_supported(tmp_path):
    f = tmp_path / "note.foo"
    f.write_text("x")
    with pytest.raises(ValueError, match=r"unsupported extension '\.foo'; supported: pdf, png, jpg, jpeg, heic"):
        FileSource().fetch_pages(str(f))
