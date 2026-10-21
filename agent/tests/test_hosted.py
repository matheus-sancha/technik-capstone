"""The hosted agent's Responses endpoint, offline: the fake model, the real server over stdio, the real host app.

The hosted server always streams the agent's run, so these tests are what prove the refusal guard
still holds once the agent is deployed.
"""
import sys
from pathlib import Path

from agent_framework import ChatResponse, ChatResponseUpdate, ResponseStream
from starlette.testclient import TestClient

AGENT = Path(__file__).parent.parent
sys.path[:0] = [str(AGENT), str(AGENT / "tests")]

from fake_model import FakeChatClient  # noqa: E402
from hosted import host  # noqa: E402
from main import REFUSAL, ROOT, TOOL_LOOP, teamcenter_server  # noqa: E402


class StreamingFakeChatClient(FakeChatClient):
    """The scripted model, streamed as the hosted server asks for it."""

    async def _inner_get_response(self, *, messages, stream, options, **kwargs):
        response = await super()._inner_get_response(messages=messages, stream=False, options=options)
        if not stream:
            return response

        async def updates():
            for m in response.messages:
                yield ChatResponseUpdate(role=m.role, contents=m.contents)
        return ResponseStream(updates(), finalizer=ChatResponse.from_updates)


def ask(question, **script):
    client = StreamingFakeChatClient(function_invocation_configuration=TOOL_LOOP, **script)
    server = teamcenter_server(args=("run", "--directory", str(ROOT), "tests/fake_server.py"))
    with TestClient(host(client, server)) as http:
        assert http.get("/readiness").status_code == 200
        response = http.post("/responses", json={"input": question, "stream": False})
    assert response.status_code == 200, response.text
    body = response.json()
    text = "".join(part["text"] for item in body["output"] if item["type"] == "message"
                   for part in item["content"] if part["type"] == "output_text")
    return body, text


def test_the_hosted_agent_answers_from_a_tool():
    answer = "Drawing DU700001042 is released at rev C, under ECN70000051."
    body, text = ask("What's the latest released revision of drawing DU700001042?",
                     calls=[("get_revision_status", {"item_no": "DU700001042"})], answer=answer)
    assert body["status"] == "completed"
    assert any(item["type"] == "function_call" for item in body["output"])
    assert text == answer


def test_the_hosted_agent_still_refuses_an_answer_from_memory():
    body, text = ask("How many shifts does Plant 2 run in winter?", answer="Plant 2 runs three shifts in winter.")
    assert text == REFUSAL
    assert "three shifts" not in str(body["output"])
