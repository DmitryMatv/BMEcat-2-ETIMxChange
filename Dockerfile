# Build stage
FROM python:3.13-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# Final stage
FROM python:3.13-slim
WORKDIR /app

# Create a non-root user
RUN adduser --disabled-password --gecos '' appuser

# Copy installed packages from the builder stage
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
# Copy executables (like uvicorn) from the builder stage's bin directory
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application files and set permissions
COPY --chown=appuser . .

USER appuser

EXPOSE 5001

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5001", "--workers", "4"]