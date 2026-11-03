"""Keep application checks offline and independent of an operator's live settings."""
import pytest


@pytest.fixture(autouse=True)
def isolated_provider_settings(monkeypatch):
    monkeypatch.setenv('LESSONTRACE_ENABLE_META','0')
    monkeypatch.setenv('LESSONTRACE_TEST_LIMIT_CENTS','100')
