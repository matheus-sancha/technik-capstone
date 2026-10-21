# Stage 5: the hosted agent. azd builds it from agent/ (see azure.yaml); Foundry runs it on port 8088.
FROM ghcr.io/astral-sh/uv:0.11.26 AS uv
FROM python:3.12-slim

COPY --from=uv /uv /bin/
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY main.py hosted.py instructions.md ./

EXPOSE 8088
CMD ["/app/.venv/bin/python", "hosted.py"]
