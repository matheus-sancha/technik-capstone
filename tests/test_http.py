"""Run the server as Container Apps does, over streamable HTTP, and read the agent's key as Key Vault supplies it."""
import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
import snowflake.connector
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from mcp import Client

import teamcenter

FAKE_SERVER = Path(__file__).parent / "fake_server.py"
REAL_CONNECT = teamcenter.connect  # conftest swaps in the fake before each test


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def http_server():
    port = free_port()
    env = {**os.environ, "PORT": str(port), "MCP_ALLOWED_HOSTS": "teamcenter-mcp.example.io"}
    process = subprocess.Popen([sys.executable, str(FAKE_SERVER), "--http"], env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://localhost:{port}/mcp"
    for _ in range(100):
        try:
            urllib.request.urlopen(url, timeout=0.2)
            break
        except urllib.error.HTTPError:
            break  # it answered, if only to say a GET needs a session
        except OSError:
            time.sleep(0.1)
    yield url
    process.terminate()
    process.wait(timeout=10)


async def call(url):
    async with Client(url) as client:
        listed = await client.list_tools()
        result = await client.call_tool("get_revision_status", {"item_no": "DU700001042"})
        return {tool.name for tool in listed.tools}, result


def test_server_answers_over_streamable_http(http_server):
    names, result = asyncio.run(call(http_server))
    assert names == {"get_document", "list_operation_documents", "get_revision_status"}
    assert "the released revision is rev C" in result.content[0].text


def test_a_request_for_another_host_name_is_refused(http_server):
    # DNS rebinding: a page that points its own name at the server must not reach the tools.
    initialize = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                  "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                             "clientInfo": {"name": "test", "version": "1"}}}
    request = urllib.request.Request(http_server, data=json.dumps(initialize).encode(), headers={
        "Host": "evil.example.com", "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"})
    with pytest.raises(urllib.error.HTTPError) as refused:
        urllib.request.urlopen(request, timeout=5)
    assert refused.value.code == 421


def test_the_key_comes_from_the_environment_when_key_vault_supplies_it(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    seen = {}
    monkeypatch.setattr(snowflake.connector, "connect", lambda **kwargs: seen.update(kwargs))
    for name in ["SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_ROLE", "SNOWFLAKE_WAREHOUSE",
                 "SNOWFLAKE_DATABASE", "SNOWFLAKE_SCHEMA"]:
        monkeypatch.setenv(name, "x")
    monkeypatch.setenv("SNOWFLAKE_PRIVATE_KEY", pem)
    monkeypatch.delenv("SNOWFLAKE_PRIVATE_KEY_FILE", raising=False)
    monkeypatch.setattr(teamcenter, "load_dotenv", lambda: None)

    REAL_CONNECT()
    assert "private_key_file" not in seen
    loaded = serialization.load_der_private_key(seen["private_key"], password=None)
    assert loaded.private_numbers() == key.private_numbers()
