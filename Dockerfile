# --- builder ---
    FROM python:3.11-slim AS builder
    COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
    WORKDIR /app
    COPY pyproject.toml uv.lock README.md ./
    RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
    
    # --- runtime ---
    FROM python:3.11-slim
    # Patch base OS packages (debian CVEs) + pip ecosystem (wheel/jaraco.context
    # CVE-2026-24049 / CVE-2026-23949 flagged by Trivy in the stock slim image)
    RUN apt-get update && apt-get -y upgrade && rm -rf /var/lib/apt/lists/* \
        && pip install --no-cache-dir --upgrade pip setuptools wheel jaraco.context
    WORKDIR /app
    COPY --from=builder /app/.venv /app/.venv
    COPY . .
    ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PORT=8080 UV_LINK_MODE=copy
    EXPOSE 8080
    CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]