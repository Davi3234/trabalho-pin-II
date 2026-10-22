FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY pyproject.toml ./
COPY ignis ./ignis
RUN pip install .

COPY alembic.ini ./
COPY migrations ./migrations
COPY seeds ./seeds

RUN useradd --create-home ignis
USER ignis

EXPOSE 8000
# migration + seed são idempotentes; rodar no start mantém o deploy em um comando só
CMD ["sh", "-c", "alembic upgrade head && python -m ignis.db.seed && uvicorn ignis.api.main:app --host 0.0.0.0 --port 8000"]
