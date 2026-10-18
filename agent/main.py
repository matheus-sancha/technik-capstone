"""The Technik Production Assistant. Stage 1: it loads its instructions and does nothing else.

Run from agent/: uv run main.py
"""
from importlib.metadata import version
from pathlib import Path

from dotenv import load_dotenv

INSTRUCTIONS = Path(__file__).parent / "instructions.md"


def main():
    load_dotenv(Path(__file__).parent.parent / ".env")
    instructions = INSTRUCTIONS.read_text(encoding="utf-8")
    print(f"Agent Framework {version('agent-framework-core')}; "
          f"instructions loaded ({len(instructions)} characters). No model and no tools yet.")


if __name__ == "__main__":
    main()
