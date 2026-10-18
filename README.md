# Technik capstone

The Technik Production Assistant, rebuilt pro-code. This is the capstone of the
[AI Academy](https://github.com/matheus-sancha/AI-Academy) Advanced level: an MCP server over
Teamcenter data in Snowflake, an Agent Framework agent that uses it, evaluations that gate it,
and a Foundry hosted deployment. Each stage is a diff you can review.

Technik, its data and its documents are **fictional, for training only**.

## Layout

| Path | What it is |
|---|---|
| `seed/` | Creates `TECHNIK_DW.OPS` in your Snowflake account: 13 tables, rows from `seed/data/*.csv`, two views, and the agent's role, warehouse and service user |
| `setup/check.py` | Proves the agent's identity reads what later stages need, and nothing more |
| `agent/` | The agent: its instructions, and its own uv project (Agent Framework) |
| `evals/eval_set.jsonl` | The evaluation set, under source control from the first commit |

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
the two views and the two tables it is granted, cannot read the tables behind the views, and gets
the known answer for one question. Every line should say `PASS`.

## Stage 1: the scaffold

```powershell
cd agent
uv run main.py
```

It loads the agent's instructions and does nothing else. That is the point: every later stage is
a change to a project that already runs.
