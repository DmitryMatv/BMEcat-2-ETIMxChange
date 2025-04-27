# Stage 1: Builder Stage - Installs dependencies
FROM python:3.13-slim AS builder
WORKDIR /app

# Install build dependencies if needed (e.g., for packages with C extensions)
#RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# Stage 2: Final Stage - Copies application and dependencies
FROM python:3.13-slim
WORKDIR /app

# Create a non-root user and group
RUN addgroup --system appuser && adduser --system --group appuser

# Copy installed packages from the builder stage
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
# Copy executables (like uvicorn) from the builder stage's bin directory
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application files and set permissions
COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost:5000/ || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5000", "--workers", "2"]