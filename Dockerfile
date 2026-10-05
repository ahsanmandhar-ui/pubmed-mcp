# ── Build stage ──────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --target=/deps -r requirements.txt

# ── Runtime stage ────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Non-root user for security
RUN adduser --disabled-password --gecos "" mcpuser
COPY --from=builder /deps /deps
ENV PYTHONPATH=/deps

COPY server.py ncbi_client.py access.py ./

# Cloud Run injects PORT; default 8080
ENV PORT=8080
ENV MCP_TRANSPORT=streamable-http
ENV PYTHONUNBUFFERED=1

USER mcpuser

EXPOSE 8080

CMD ["python", "server.py"]
