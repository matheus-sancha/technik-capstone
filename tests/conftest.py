import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path[:0] = [str(ROOT / "server"), str(ROOT / "tests")]

import teamcenter  # noqa: E402
from fakes import FakeConnection  # noqa: E402


@pytest.fixture(autouse=True)
def fake_snowflake(monkeypatch):
    """Every test reads seed/data through the fake, never a real account."""
    monkeypatch.setattr(teamcenter, "connect", FakeConnection)
    teamcenter.connection.cache_clear()
    yield
    teamcenter.connection.cache_clear()
