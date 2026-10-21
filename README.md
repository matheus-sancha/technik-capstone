# Technik capstone

The Technik Production Assistant, rebuilt pro-code. This is the capstone of the
[AI Academy](https://github.com/matheus-sancha/AI-Academy) Advanced level: an MCP server over
Teamcenter data in Snowflake, an Agent Framework agent that uses it, evaluations that gate it,
and a Foundry hosted deployment. Each stage is a diff you can review.

Technik, its data and its documents are **fictional, for training only**.

## Layout

| Path | What it is |
|---|---|
| `seed/` | Creates `TECHNIK_DW.OPS` in your Snowflake account: 13 tables, rows from `seed/data/*.csv`, three views, and the agent's role, warehouse and service user |
| `setup/check.py` | Proves the agent's identity reads what later stages need, and nothing more |
| `server/teamcenter.py` | Stage 2: the MCP server over Teamcenter, with three tools |
| `tests/` | Offline tests: a fake Snowflake built from `seed/data/`, and the server spawned over stdio |
| `agent/` | Stage 3: the agent, its instructions and offline tests, in its own uv project (Agent Framework) |
| `evals/` | Stage 4: the evaluation set (under source control from the first commit), its runner, the offline replay and the baseline |
| `.github/workflows/evals.yml` | Runs the tests and the evals on every pull request, and lints the Bicep |
| `infra/` | Stage 5: Bicep for the server's side on Azure: Key Vault, a registry, Container Apps, its Entra app |
| `azure.yaml` | Stage 5: the Foundry side: the project, the model, the server's connection, the toolbox and the hosted agent |
| `.github/workflows/release.yml` | Stage 5: the release: the evals as the gate, then the deployment, then Foundry's report |

There are two uv projects. The root one (seed, setup check and, from stage 2, the MCP server) uses
MCP Python SDK v2. `agent/` has its own, because Agent Framework's MCP client still requires
`mcp<2`. The server and the agent talk over the protocol, so their SDK versions don't need to match.

## Before you start

You need Python 3.12, [uv](https://docs.astral.sh/uv/), a Snowflake account (a trial works), and
an admin user there who can use `SYSADMIN` and `SECURITYADMIN`, with a programmatic access token.

```powershell
git clone https://github.com/matheus-sancha/technik-capstone
cd technik-capstone
Copy-Item .env.example .env
```

Fill in `.env`: your account identifier, the admin user and its token, and a warehouse the admin
can use. `.env` and `keys/` are gitignored. Never commit them.

## Seed Snowflake

```powershell
uv run seed/seed.py
```

This creates the database, loads the rows, creates the views, and creates `TECHNIK_AGENT_RO`,
`TECHNIK_AGENT_WH` and the service user `TECHNIK_AGENT_SVC`. On the first run it writes the
service user's private key to `keys/technik_agent_svc.p8`. Running it again resets the data.

## Check the setup

```powershell
uv run setup/check.py
```

It connects as `TECHNIK_AGENT_SVC`, with its key and nothing else, and checks that the role reads
the three views and the two tables it is granted, cannot read the tables behind the views, and gets
the known answer for one question. Every line should say `PASS`.

## Stage 1: the scaffold

```powershell
cd agent
uv run main.py
```

At stage 1 it loaded the agent's instructions and did nothing else. That is the point: every later
stage is a change to a project that already runs. From stage 3 the same command asks the model a
question, so it needs the Foundry settings below.

## Stage 2: an MCP server over Teamcenter

`server/teamcenter.py` is an MCP server (Python SDK v2) with three read-only tools:

| Tool | Reads | Answers |
|---|---|---|
| `get_document` | `TC_DOCUMENTS` | A document's title, type, owner and every revision with its status |
| `list_operation_documents` | `V_OPERATION_DOCUMENTS` | The drawing, CNC program and work instruction a work order operation uses |
| `get_revision_status` | `V_RELEASED_REVISIONS` | Whether a revision is the released one, and which change notice released it |

It connects as `TECHNIK_AGENT_SVC`, the identity `setup/check.py` proved. VS Code starts it over
stdio from `.vscode/mcp.json`: open the repo folder, start the server from that file, and ask agent
mode about work order `100004510`.

```powershell
uv run pytest
```

The tests never touch Snowflake. They load `seed/data/` into an in-memory fake that exposes only
the granted objects, call each tool, and spawn the server over stdio to call it through an MCP
client.

## Stage 3: the agent

`agent/main.py` is an Agent Framework agent. It calls a Foundry model deployment, and its tools come
from the stage 2 server, which it starts over stdio in the root project. Add your Foundry project
endpoint and model deployment (`FOUNDRY_MODEL`, `gpt-4.1-mini` by default) to `.env`, sign in with
`az login`, then ask it something:

```powershell
cd agent
uv run main.py "Which documents does operation 0010 of work order 100004510 use?"
```

Its instructions, `agent/instructions.md`, are layered: role, tone, tasks, instructions, rules and
a refusal. The refusal is also enforced in code. If no tool result backs an answer, the answer came
from the model's memory, and `grounded_or_refuse` replaces it with the refusal. A lookup that finds
nothing still counts as backed, because the server's error says what was wrong.

```powershell
cd agent
uv run pytest
```

These tests never touch Snowflake or Azure. A scripted fake model drives Agent Framework's real
tool loop, and the real server runs as a subprocess with the fake Snowflake. They check one
answered question, one failed lookup, and one answer from memory that becomes the refusal.

## Stage 4: the evals

`evals/eval_set.jsonl` is the versioned evaluation set. Each case has a question, a ground truth,
the tool calls it should make and the facts its answer must contain. `evals/run.py` runs every case
through the agent with Agent Framework's `evaluate_agent`, then grades it. Three code checks always
run: `tool_calls_present`, `tool_call_args_match` and `facts_present`. In a live run, Foundry's
judges are added: intent resolution, task adherence and tool call accuracy. The report compares
the run with `evals/baseline.json` and fails on a regression, meaning a case the baseline passes
and this run doesn't.

```powershell
cd agent
uv run ../evals/run.py --offline
```

Offline, a replayed model stands in for Foundry. `evals/replay.jsonl` holds one plausible model
turn per case, and the fake Snowflake stands in for the real one. One case fails on purpose.
For `rev-03`, the replay checks the revision and then calls the unreleased revision C current anyway.
A tool result backs that answer, so the refusal guard lets it through, and only a grader catches it.
The baseline records it as a known failure. It shows up red in every report but doesn't block a merge.

`.github/workflows/evals.yml` runs the server tests, the agent tests and the offline evals on every
pull request that touches the agent, the server, the evals or the data. The report goes to the run's
summary and is uploaded as an artifact. Its `live` job is off until you set the repository variable
`EVALS_LIVE` to `true`. It then needs these variables: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`,
`AZURE_SUBSCRIPTION_ID` (for OpenID Connect sign-in), `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_MODEL` and
`SNOWFLAKE_ACCOUNT`. It also needs one secret, `SNOWFLAKE_PRIVATE_KEY`, which holds the contents of
`keys/technik_agent_svc.p8`. A live run has no baseline at first. Run
`uv run ../evals/run.py --update-baseline` once, read the report, and commit the baseline. That
commit is what a review approves.

## Stage 5: ship it

Two things go to Azure. The stage 2 server runs on Azure Container Apps over streamable HTTP, and
the agent runs as a Foundry hosted agent with its own Microsoft Entra Agent ID. The agent doesn't
start the server anymore. It reaches the server through a Foundry toolbox, and Foundry calls the
server with a token for the agent's identity. The server's app answers only identities that hold
its `Teamcenter.Read` role, so the agent is the only caller.

| File | What it deploys |
|---|---|
| `infra/base.bicep` | Key Vault, a container registry, the Container Apps environment, Application Insights, the server's managed identity, and the server's Entra app with its role |
| `server/Dockerfile`, `infra/server.bicep` | The server image and its Container App, with Entra built-in authentication. Key Vault supplies the Snowflake key |
| `agent/hosted.py`, `agent/Dockerfile` | The agent behind the Responses protocol, with its tools from the toolbox |
| `azure.yaml` | The Foundry project and model deployment, the `teamcenter` connection (agent identity), the `technik-tools` toolbox and the hosted agent |

You need the Azure CLI, the Azure Developer CLI 1.32 or later, and Docker, which builds the agent's
image. Use a region where hosted agents are available.

```powershell
az login
azd auth login
azd ext install microsoft.foundry
```

1. Create the resource group and the server's side:

   ```powershell
   az group create -n rg-technik -l swedencentral
   az deployment group create -g rg-technik -f infra/base.bicep --query properties.outputs
   ```

2. Put the agent's Snowflake key in the vault. It never goes into an image or a setting:

   ```powershell
   az keyvault secret set --vault-name <keyVaultName> -n snowflake-private-key --file keys/technik_agent_svc.p8
   ```

3. Build the server's image in the registry, then deploy its Container App:

   ```powershell
   az acr build -r <registryName> -t teamcenter-mcp:1 -f server/Dockerfile .
   az deployment group create -g rg-technik -f infra/server.bicep --query properties.outputs.url.value `
     -p image=<registryLoginServer>/teamcenter-mcp:1 snowflakeAccount=<your-account>
   ```

4. Tell azd where the server is and which audience its tokens need:

   ```powershell
   azd env new technik
   azd env set AZURE_LOCATION swedencentral
   azd env set TEAMCENTER_MCP_URL <url>
   azd env set TEAMCENTER_AUDIENCE <audience>
   ```

5. Provision the Foundry project, the model and the connection, then deploy the toolbox and the agent:

   ```powershell
   azd up
   ```

6. Give the agent's identity the server's role. Until you do, Entra refuses it a token and every tool
   call fails:

   ```powershell
   $agent = (azd ai agent show --output json | ConvertFrom-Json).instance_identity.principal_id
   $body = @{ principalId = $agent; resourceId = "<serverPrincipalId>"; appRoleId = "<readRoleId>" } | ConvertTo-Json
   az rest --method post --body $body `
     --url "https://graph.microsoft.com/v1.0/servicePrincipals/<serverPrincipalId>/appRoleAssignedTo"
   ```

7. Turn on tracing. In the Foundry portal, open the project, select **Agents**, then **Traces**, and
   connect the Application Insights resource `base.bicep` created. The hosted agent already emits
   OpenTelemetry. Foundry injects the connection string once the resource is connected.

8. Ask it something, then read the trace in **Traces**:

   ```powershell
   azd ai agent invoke "Which documents does operation 0010 of work order 100004510 use?"
   ```

Anyone with access to the Foundry project can open the agent in the portal's playground.

### What the offline checks cover

```powershell
uv run pytest
cd agent
uv run pytest
```

The root suite runs the server over streamable HTTP, refuses a request for another host name, and
reads the key the way Key Vault supplies it. It also validates `azure.yaml` against azd's own
schemas, vendored in `infra/schemas/`, and checks that the Bicep, the Dockerfiles and the code agree
on ports, variables and the audience. The agent suite drives the hosted Responses endpoint in
process. The hosted server always streams, so the refusal guard holds a streamed answer until it
knows a tool backed it. CI also lints both Bicep files and builds both images, without pushing them.

### The release

`.github/workflows/release.yml` runs on a `v*` tag once you set the repository variable `SHIP_LIVE`
to `true`. It runs the evals workflow first, and a regression stops the release there. Then
`azd deploy` creates a new agent version, and `microsoft/ai-agent-evals` runs Foundry's judges on the
new version and the one it replaced, with `evals/action_dataset.json`. That report goes to the run
summary and doesn't block anything. After you change `evals/eval_set.jsonl`, regenerate the dataset
from `agent/` with `uv run ../evals/action_dataset.py`. Besides the variables the live evals need,
the release needs `AZURE_ENV_NAME`, `AZURE_LOCATION`, `FOUNDRY_PROJECT_ENDPOINT`,
`TEAMCENTER_MCP_URL` and `TEAMCENTER_AUDIENCE`.
