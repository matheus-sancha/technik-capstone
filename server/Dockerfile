# Stage 5: the Teamcenter MCP server for Azure Container Apps. Build from the repo root:
#   az acr build -r <your-registry> -t teamcenter-mcp:1 -f server/Dockerfile .
FROM ghcr.io/astral-sh/uv:0.11.26 AS uv
FROM python:3.12-slim

COPY --from=uv /uv /bin/
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY server/ server/

# Streamable HTTP on /mcp. Key Vault supplies SNOWFLAKE_PRIVATE_KEY; never bake it into the image.
EXPOSE 8000
CMD ["/app/.venv/bin/python", "server/teamcenter.py", "--http"]
