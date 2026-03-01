"""Shared pytest fixtures for all test suites."""
import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
CONFIG_DIR = REPO_ROOT / "config"


@pytest.fixture
def config_dir():
    return CONFIG_DIR
