"""The Technik Production Assistant. Stage 3: an Agent Framework agent with the stage 2 server as its tools.

Run from agent/: uv run main.py "What's the latest released revision of drawing DU700001042?"
"""
import asyncio
import shutil
import sys
from pathlib import Path

from agent_framework import Agent, AgentContext, MCPStdioTool, Message, agent_middleware
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
INSTRUCTIONS = Path(__file__).parent / "instructions.md"
REFUSAL = ("I can't answer that from Teamcenter. I can look up a controlled document, the documents "
           "a work order operation uses, and the released revision of a part, drawing, CNC program "
           "or document.")

# Pass the server's ToolError messages to the model; by default it sees only "Error: Function failed."
TOOL_LOOP = {"include_detailed_errors": True, "max_function_calls": 6}


@agent_middleware
async def grounded_or_refuse(context: AgentContext, call_next):
    """An answer that no tool result backs came from the model's memory: replace it with the refusal."""
    await call_next()
    response = context.result
    if context.stream or response is None:
        return
    if not any(c.type == "function_result" for m in response.messages for c in m.contents):
        response.messages = [Message(role="assistant", contents=[REFUSAL])]


def teamcenter_server(command="uv", args=("run", "--directory", str(ROOT), "server/teamcenter.py")):
    """The stage 2 server over stdio, run in the root project, which holds MCP SDK v2."""
    return MCPStdioTool(name="teamcenter", command=shutil.which(command) or command, args=list(args),
                        load_prompts=False, tool_result_content="content_first")


def build_agent(client, server):
    return Agent(client=client, name="technik-production-assistant",
                 instructions=INSTRUCTIONS.read_text(encoding="utf-8"),
                 tools=server, middleware=[grounded_or_refuse])


async def ask(question):
    from agent_framework.foundry import FoundryChatClient
    from azure.identity.aio import AzureCliCredential

    async with AzureCliCredential() as credential, teamcenter_server() as server:
        client = FoundryChatClient(credential=credential, function_invocation_configuration=TOOL_LOOP)
        agent = build_agent(client, server)
        print((await agent.run(question)).text)


if __name__ == "__main__":
    load_dotenv(ROOT / ".env")
    asyncio.run(ask(" ".join(sys.argv[1:]) or "What's the latest released revision of drawing DU700001042?"))
