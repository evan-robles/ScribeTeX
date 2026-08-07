from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "macapp" / "ScribeTeX"


def test_review_window_source_exists():
    assert (APP / "ReviewWindow.swift").exists()


def test_bridge_has_refile_knowncourses_discard():
    b = (APP / "Bridge.swift").read_text()
    for cmd in ("refile", "known-courses", "discard"):
        assert cmd in b, f"Bridge missing {cmd}"


def test_bridge_has_compile_build_openpdf():
    b = (APP / "Bridge.swift").read_text()
    for cmd in ("compile", "build", "open-pdf"):
        assert cmd in b, f"Bridge missing {cmd}"


def test_app_uses_usernotifications_and_window():
    app = (APP / "ScribeTeXApp.swift").read_text()
    assert "UserNotifications" in app or "UNUserNotificationCenter" in app
    review = (APP / "ReviewWindow.swift").read_text()
    # window pulls parked notes + files them
    assert "needsReview" in review or "ReviewItem" in review
    assert "refile" in review.lower()


def test_models_review_item_has_guess_fields():
    m = (APP / "Models.swift").read_text()
    for f in ("course", "section", "subsection", "date"):
        assert f in m
