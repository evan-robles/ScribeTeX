import pytest
from automation import config


def test_non_numeric_sweep_seconds_clear_error():
    with pytest.raises(ValueError, match=r"SCRIBETEX_SWEEP_SECONDS.*not a valid integer"):
        config.load_config(env={"SCRIBETEX_SWEEP_SECONDS": "soon"}, toml_path=None)


def test_non_numeric_settle_seconds_clear_error():
    with pytest.raises(ValueError, match=r"SCRIBETEX_SETTLE_SECONDS.*not a valid integer"):
        config.load_config(env={"SCRIBETEX_SETTLE_SECONDS": "abc"}, toml_path=None)


def test_valid_numeric_still_works():
    cfg = config.load_config(
        env={"SCRIBETEX_SWEEP_SECONDS": "120", "SCRIBETEX_SETTLE_SECONDS": "2"},
        toml_path=None,
    )
    assert cfg["sweep_seconds"] == 120
    assert cfg["settle_seconds"] == 2
