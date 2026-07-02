FROM python:3.14-alpine AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

RUN apk add --no-cache \
    build-base \
    cargo \
    libxml2-dev \
    libxslt-dev \
    rust

RUN python -m venv "$VIRTUAL_ENV"

COPY requirements.txt .
RUN pip install --root-user-action=ignore -r requirements.txt

FROM python:3.14-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

RUN apk add --no-cache curl libxml2 libxslt && \
    addgroup -S appgroup && \
    adduser -S -G appgroup appuser

COPY --from=builder /opt/venv /opt/venv
COPY --chown=appuser:appgroup . .

USER appuser

EXPOSE 5001

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5001"]
