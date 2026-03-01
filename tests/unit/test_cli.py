"""Unit tests for CLI bootstrap behavior."""

from __future__ import annotations

from unittest.mock import patch

from click.testing import CliRunner

from router.cli import cli


def test_cli_loads_dotenv_for_providers_commands() -> None:
    runner = CliRunner()

    with patch("router.cli.load_dotenv") as mock_dotenv, \
         patch("router.cli._load"), \
         patch("router.cli.list_providers", return_value=[]):
        result = runner.invoke(cli, ["providers", "list"])

    assert result.exit_code == 0
    mock_dotenv.assert_called_once()
