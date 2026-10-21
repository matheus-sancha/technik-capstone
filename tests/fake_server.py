"""The real stage 2 server, started over stdio with the fake Snowflake connection in place of the real one.

The stdio and HTTP tests spawn this file, so the protocol, the process and the tool code are all real.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path[:0] = [str(ROOT / "server"), str(ROOT / "tests")]

import teamcenter  # noqa: E402
from fakes import FakeConnection  # noqa: E402

teamcenter.connect = FakeConnection

if __name__ == "__main__":
    teamcenter.serve_http() if "--http" in sys.argv else teamcenter.mcp.run()
