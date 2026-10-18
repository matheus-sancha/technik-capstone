"""Spawn the server as VS Code would, over stdio, and call each tool through a real MCP client."""
import asyncio
import sys
from pathlib import Path

from mcp import Client
from mcp.client.stdio import StdioServerParameters

SERVER = StdioServerParameters(command=sys.executable, args=[str(Path(__file__).parent / "fake_server.py")])
TOOLS = {"get_document", "list_operation_documents", "get_revision_status"}


async def session():
    async with Client(SERVER) as client:
        listed = await client.list_tools()
        calls = {
            "document": await client.call_tool("get_document", {"doc_no": "SOP70000101"}),
            "operation": await client.call_tool("list_operation_documents",
                                                {"work_order": "100004521", "operation_seq": "0020"}),
            "revision": await client.call_tool("get_revision_status", {"item_no": "SWI70000318"}),
            "bad_input": await client.call_tool("get_document", {"doc_no": "quality handling"}),
        }
        return {tool.name for tool in listed.tools}, calls


def text(result):
    return result.content[0].text


def test_server_answers_over_stdio():
    names, calls = asyncio.run(session())
    assert names == TOOLS
    assert text(calls["document"]).startswith("SOP70000101: Quality Notification Handling (SOP)")
    assert text(calls["operation"]).splitlines()[1] == "  Document SWI70000318, the current released revision"
    assert "the released revision is rev B" in text(calls["revision"])
    assert calls["bad_input"].is_error and not calls["document"].is_error
