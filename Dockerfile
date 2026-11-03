# The agent API (tda.api). Multi-arch: the same file builds for linux/amd64 (the laptop) and
# linux/arm64 (the OCI Ampere VM). Oracle and Ollama run outside it; settings come from the environment.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH=/opt/venv/bin:$PATH

# uv from PyPI, not GitHub release assets (slow on this network).
RUN pip install --no-cache-dir uv==0.13.6

WORKDIR /app
# Dependencies first, so a code change doesn't reinstall them. No dev group, no laya extra (torch).
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY db ./db
RUN uv sync --frozen --no-dev

RUN useradd --system --no-create-home app
USER app
EXPOSE 8000
CMD ["uvicorn", "tda.api:app", "--host", "0.0.0.0", "--port", "8000"]
