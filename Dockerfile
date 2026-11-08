# --- builder ---
    FROM python:3.11-slim AS builder
    COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
    WORKDIR /app
    COPY pyproject.toml uv.lock README.md ./
    RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
    
    # --- runtime ---
    FROM python:3.11-slim
    WORKDIR /app
    COPY --from=builder /app/.venv /app/.venv
    COPY . .
    ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PORT=8080
    EXPOSE 8080
    CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]