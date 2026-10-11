"""RAVEN entry point: `python main.py` starts the CLI chat."""
import sys

from core.cli import main

if __name__ == "__main__":
    sys.exit(main())