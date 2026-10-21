"""Stage 5: the agent as a Foundry hosted agent, serving the Responses protocol on port 8088.

Its tools come from the Foundry toolbox, which reaches the stage 2 server on Container Apps with the
agent's own Entra identity. Foundry injects FOUNDRY_PROJECT_ENDPOINT and the Application Insights
connection string; azure.yaml sets the model deployment and the toolbox name.

Run locally from agent/ with `azd ai agent run`, or deploy with `azd deploy technik-agent`.
"""
import os

from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import FoundryToolbox, ResponsesHostServer
from azure.identity import DefaultAzureCredential

from main import TOOL_LOOP, build_agent


def host(client, tools):
    # Foundry keeps the conversation, so the model call stores nothing.
    return ResponsesHostServer(build_agent(client, tools, default_options={"store": False}))


if __name__ == "__main__":
    credential = DefaultAzureCredential()
    client = FoundryChatClient(project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
                               model=os.environ["MICROSOFT_FOUNDRY_MODEL_DEPLOYMENT_NAME"],
                               credential=credential, function_invocation_configuration=TOOL_LOOP)
    # The toolbox URL is built from FOUNDRY_PROJECT_ENDPOINT and TOOLBOX_NAME, so it follows the default version.
    host(client, FoundryToolbox(credential)).run()
