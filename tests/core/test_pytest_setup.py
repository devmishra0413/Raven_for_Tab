# tests/core/test_pytest_setup.py – just check conftest imported
from pathlib import Path

def test_config_file_exists():
    assert Path("config.json").is_file()
