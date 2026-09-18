FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .
COPY alembic ./alembic
COPY alembic.ini ./
COPY docs ./docs
RUN mkdir -p /app/data/uploads
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
