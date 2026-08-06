import fitz
from PIL import Image
from automation import readiness


def _pdf(path, pages=1):
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page()
    doc.save(str(path))
    doc.close()
    return path


def test_stable_when_size_unchanged():
    sizes = iter([100, 100])
    ok = readiness.is_stable(
        "x", 1, size_fn=lambda p: next(sizes), sleep_fn=lambda s: None
    )
    assert ok is True


def test_not_stable_when_growing():
    sizes = iter([100, 250])
    ok = readiness.is_stable(
        "x", 1, size_fn=lambda p: next(sizes), sleep_fn=lambda s: None
    )
    assert ok is False


def test_not_stable_when_zero():
    ok = readiness.is_stable(
        "x", 1, size_fn=lambda p: 0, sleep_fn=lambda s: None
    )
    assert ok is False


def test_valid_pdf(tmp_path):
    p = _pdf(tmp_path / "n.pdf")
    assert readiness.is_valid_note(p) is True


def test_valid_png(tmp_path):
    p = tmp_path / "n.png"
    Image.new("RGB", (10, 10), "white").save(p)
    assert readiness.is_valid_note(p) is True


def test_invalid_zero_byte_pdf(tmp_path):
    p = tmp_path / "empty.pdf"
    p.write_bytes(b"")
    assert readiness.is_valid_note(p) is False


def test_invalid_truncated_pdf(tmp_path):
    p = tmp_path / "trunc.pdf"
    p.write_bytes(b"%PDF-1.4 broken not really a pdf")
    assert readiness.is_valid_note(p) is False


def test_unsupported_ext(tmp_path):
    p = tmp_path / "note.txt"
    p.write_text("hi")
    assert readiness.is_valid_note(p) is False


def test_is_ready_combines(tmp_path):
    p = _pdf(tmp_path / "n.pdf")
    ok = readiness.is_ready(
        p, 1, size_fn=lambda x: p.stat().st_size, sleep_fn=lambda s: None
    )
    assert ok is True
