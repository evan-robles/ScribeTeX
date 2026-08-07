from automation import appcli, config


def _cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRIBETEX_NOTES_ROOT", str(tmp_path / "notes"))
    return config.load_config(env={"SCRIBETEX_INBOX": str(tmp_path)}, toml_path=None)


def test_courses_info_reports_metadata(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    from scribetex import server
    server._write_section("Bio", "\\section{A}\nx", "2026-08-06", source_name="n.pdf")
    (tmp_path / "notes" / "Bio" / "flashcards.tsv").write_text("q\ta\nq2\ta2\n")
    r = appcli._courses_info(cfg)
    assert r["ok"] is True
    bio = next(c for c in r["courses"] if c["name"] == "Bio")
    assert bio["note_count"] == 1
    assert bio["flashcard_count"] == 2
    assert bio["has_pdf"] is False        # not compiled
    assert bio["has_guide"] is False


def test_courses_info_counts_needs_review(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    from scribetex import server
    server._write_section("Bio", "\\section{A}\nx", "2026-08-06", source_name="n.pdf")
    nr = tmp_path / "NeedsReview"; nr.mkdir(parents=True, exist_ok=True)
    (nr / "parked.pdf").write_bytes(b"%PDF")
    r = appcli._courses_info(cfg)
    assert all(c["needs_review"] == 1 for c in r["courses"])


def test_read_flashcards_parses_tsv(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    from scribetex import server
    server._write_section("Bio", "\\section{A}\nx", "2026-08-06", source_name="n.pdf")
    (tmp_path / "notes" / "Bio" / "flashcards.tsv").write_text(
        "What detects light?\tPhotoreceptors.\n\nBad line no tab\n")
    r = appcli._read_flashcards(cfg, "Bio")
    assert r["ok"] is True
    assert r["cards"] == [{"q": "What detects light?", "a": "Photoreceptors."}]


def test_read_flashcards_missing(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    from scribetex import server
    server._write_section("Bio", "\\section{A}\nx", "2026-08-06", source_name="n.pdf")
    assert appcli._read_flashcards(cfg, "Bio")["ok"] is False


def test_compile_guide_missing_file(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    from scribetex import server
    server._write_section("Bio", "\\section{A}\nx", "2026-08-06", source_name="n.pdf")
    r = appcli._compile_guide(cfg, "Bio")
    assert r["ok"] is False  # study-guide.tex not generated yet
