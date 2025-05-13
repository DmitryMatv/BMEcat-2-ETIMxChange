# Build stage
FROM python:3.13-alpine AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# Final stage
FROM python:3.13-alpine
WORKDIR /app

# Install curl (for healthcheck) and remove wget
RUN apk update && \
    apk add --no-cache curl && \
    rm -rf /var/cache/apk/*

# Create a non-root user and group
RUN addgroup -S appgroup && adduser -S -G appgroup appuser

# Copy installed packages from the builder stage
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
# Copy executables (like uvicorn) from the builder stage's bin directory
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application files and set permissions
COPY --chown=appuser:appgroup . .

USER appuser

EXPOSE 5001

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5001"]