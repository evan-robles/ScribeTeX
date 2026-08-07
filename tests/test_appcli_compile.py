import json
from automation import appcli, config, prompt


def _cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("SCRIBETEX_NOTES_ROOT", str(tmp_path / "notes"))
    return config.load_config(env={"SCRIBETEX_INBOX": str(tmp_path)}, toml_path=None)


def _course(tmp_path, name="Bio"):
    from scribetex.classify import course_slug
    d = tmp_path / "notes" / course_slug(name)
    d.mkdir(parents=True, exist_ok=True)
    (d / "main.tex").write_text("doc")
    return d / "main.tex"


def test_compile_reports_missing_toolchain_or_file(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    r = appcli._compile(cfg, "Nonexistent")
    assert r["ok"] is False


def test_build_fast_path_when_already_compiles(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    _course(tmp_path, "Bio")
    # Stub compile_course to report success so no real TeX is needed; the fast
    # path must skip the LLM worker entirely.
    import scribetex.compile as C
    monkeypatch.setattr(C, "compile_course",
                        lambda p, **k: {"compiled": True, "pdf": str(p) + ".pdf"})
    monkeypatch.setattr(C, "toolchain_missing", lambda: None)
    called = {"worker": False}
    def worker(*a, **k):
        called["worker"] = True
        return ""
    r = appcli._build(cfg, "Bio", invoke_fn=worker)
    assert r["ok"] is True and r["rounds"] == 0
    assert called["worker"] is False  # fast path, no LLM


def test_build_invokes_worker_on_failure(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    _course(tmp_path, "Bio")
    import scribetex.compile as C
    monkeypatch.setattr(C, "toolchain_missing", lambda: None)
    monkeypatch.setattr(C, "compile_course",
                        lambda p, **k: {"compiled": False, "errors": [{"message": "boom", "line": 5}]})

    def worker(prompt_text, claude_bin):
        # Echo a compiled result under the prompt's nonced prefix.
        import re
        m = re.search(r"SCRIBETEX_RESULT_[0-9a-f]+:", prompt_text)
        prefix = m.group(0)
        return f'{prefix} {{"status":"compiled","course":"Bio","pdf":"/x.pdf","rounds":2,"patched":["2026-08-06:a-pdf"]}}'
    r = appcli._build(cfg, "Bio", invoke_fn=worker)
    assert r["ok"] is True and r["compiled"] is True and r["rounds"] == 2


def test_build_reports_failure_when_unfixable(tmp_path, monkeypatch):
    cfg = _cfg(tmp_path, monkeypatch)
    _course(tmp_path, "Bio")
    import scribetex.compile as C
    monkeypatch.setattr(C, "toolchain_missing", lambda: None)
    monkeypatch.setattr(C, "compile_course",
                        lambda p, **k: {"compiled": False, "errors": [{"message": "boom"}]})

    def worker(prompt_text, claude_bin):
        import re
        prefix = re.search(r"SCRIBETEX_RESULT_[0-9a-f]+:", prompt_text).group(0)
        return f'{prefix} {{"status":"failed","course":"Bio","rounds":3,"errors":["still broken"]}}'
    r = appcli._build(cfg, "Bio", invoke_fn=worker)
    assert r["ok"] is False and r["compiled"] is False
