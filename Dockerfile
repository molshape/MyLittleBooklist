FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# demo.db* : optional, Build klappt auch ohne (dann Demo-Seed über OpenLibrary)
COPY app.py schema.sql demo.db* ./
COPY templates templates
COPY static static

ENV PATH="/app/.venv/bin:$PATH" DB_PATH=/data/books.db
VOLUME /data
EXPOSE 8000
# --preload: DB-Init läuft einmal vor dem Forken der Worker
CMD ["gunicorn", "--preload", "--workers", "2", "--threads", "4", "--bind", "0.0.0.0:8000", "app:app"]
