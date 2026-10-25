FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app.py schema.sql demo.py ./
COPY templates templates
COPY static static
COPY translations translations

ENV PATH="/app/.venv/bin:$PATH"
RUN pybabel compile -d translations

ENV DB_PATH=/data/books.db
VOLUME /data
EXPOSE 8000
# --preload: DB init runs once before the workers are forked
CMD ["gunicorn", "--preload", "--workers", "2", "--threads", "4", "--bind", "0.0.0.0:8000", "app:app"]
