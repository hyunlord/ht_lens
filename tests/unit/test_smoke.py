"""Phase 0 smoke tests — package importable, version present, settings load."""

from ht_lens import __version__
from ht_lens.config import Settings, get_settings
from ht_lens.logging import configure_logging, get_logger


def test_version_string() -> None:
    assert isinstance(__version__, str)
    assert __version__ == "0.0.0"


def test_settings_default() -> None:
    settings = get_settings()
    assert isinstance(settings, Settings)
    assert settings.log_level == "INFO"


def test_logging_setup() -> None:
    configure_logging("INFO")
    logger = get_logger("ht_lens.test")
    logger.info("smoke", phase=0)
