"""Run the agent loop against the fake model, with the real stage 2 server (fake Snowflake) as its tools."""
import asyncio
import sys
from pathlib import Path

AGENT = Path(__file__).parent.parent
sys.path[:0] = [str(AGENT), str(AGENT / "tests")]

from fake_model import FakeChatClient  # noqa: E402
from main import REFUSAL, ROOT, TOOL_LOOP, build_agent, teamcenter_server  # noqa: E402

TOOLS = ["get_document", "list_operation_documents", "get_revision_status"]


async def run(client, question):
    # The root project's Python runs the server, as in main.py, with the fake connection swapped in.
    async with teamcenter_server(args=("run", "--directory", str(ROOT), "tests/fake_server.py")) as server:
        return await build_agent(client, server).run(question)


def model(**script):
    return FakeChatClient(function_invocation_configuration=TOOL_LOOP, **script)


def tool_results(response):
    return [c for m in response.messages for c in m.contents if c.type == "function_result"]


def test_agent_calls_a_tool_and_answers_from_it():
    fake = model(calls=[("list_operation_documents", {"work_order": "100004510", "operation_seq": "0010"})],
                 answer="Drawing DU700001042 rev B; rev C is released under ECN70000051.")
    response = asyncio.run(run(fake, "Which documents does operation 0010 of work order 100004510 use?"))
    offered = fake.seen[0]
    assert [tool.name for tool in offered["tools"]] == TOOLS
    assert "<refusal>" in offered["instructions"]
    [result] = tool_results(response)
    assert "DU700001042" in str(result.result) and not result.exception
    assert response.text == fake.answer


def test_a_lookup_that_finds_nothing_still_counts_as_grounded():
    fake = model(calls=[("get_document", {"doc_no": "SWI70000381"})],
                 answer="There is no document SWI70000381. Did you mean SWI70000318?")
    response = asyncio.run(run(fake, "What does SWI70000381 say about weld prep?"))
    [result] = tool_results(response)
    # The server's ToolError reaches the model word for word, so it can tell the user what was wrong.
    assert "No document SWI70000381 in Teamcenter" in str(result.result) and result.exception
    assert response.text == fake.answer


def test_an_answer_no_tool_backs_becomes_the_refusal():
    fake = model(answer="Plant 2 runs three shifts in winter.")
    response = asyncio.run(run(fake, "How many shifts does Plant 2 run in winter?"))
    assert not tool_results(response)
    assert response.text == REFUSAL


def test_the_instructions_give_the_refusal_word_for_word():
    instructions = " ".join((AGENT / "instructions.md").read_text(encoding="utf-8").split())
    assert f'"{REFUSAL}"' in instructions
