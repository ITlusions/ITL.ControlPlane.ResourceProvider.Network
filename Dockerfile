# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src/ ./src/

# docker build --secret id=forgejo_token,env=FORGEJO_PACKAGE_TOKEN .
RUN --mount=type=secret,id=forgejo_token \
    pip install --no-cache-dir \
      --index-url "https://itladmin:$(cat /run/secrets/forgejo_token)@git.itlusions.com/api/packages/ITlusions/pypi/simple/" \
      --extra-index-url https://pypi.org/simple/ \
      -e .

EXPOSE 8004

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8004/health')" || exit 1

CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8004"]
