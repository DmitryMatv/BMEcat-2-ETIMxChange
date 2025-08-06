# Build stage
FROM python:3.13.5-slim-bookworm AS builder
WORKDIR /app
COPY requirements.txt .

# Install build dependencies for C (lxml) and Rust (orjson, jsonschema-rs)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    libxml2-dev \
    libxslt1-dev \
    python3-dev \
    pkg-config && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r requirements.txt


# Final stage
FROM python:3.13.5-slim-bookworm
WORKDIR /app

# Install curl (for healthcheck) and runtime libraries for lxml
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    libxml2 \
    libxslt1.1 && \
    rm -rf /var/lib/apt/lists/*

# Create a non-root user and group
RUN groupadd -r appgroup && useradd -r -g appgroup appuser

# Copy installed packages from the builder stage
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
# Copy executables (like uvicorn) from the builder stage's bin directory
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application files and set permissions
COPY --chown=appuser:appgroup . .

USER appuser

EXPOSE 5001

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5001"]