"""Shared test settings."""
import pytest

from grownet import published


@pytest.fixture(autouse=True)
def _no_published_all_network(monkeypatch):
    """Tests never reach GitHub: the daily All network (#96) is absent unless a test provides one."""
    monkeypatch.setattr(published, "fetch", lambda *a, **k: None)
