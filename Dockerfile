FROM python:3.13-slim

# Set environment variables
ENV PORT=5000

WORKDIR /app

# Create a non-root user and group
RUN addgroup --system app && adduser --system --group app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt && \
    rm -rf /root/.cache/pip

COPY . .

# Change ownership to the non-root user
RUN chown -R app:app /app

# Switch to the non-root user
USER app

EXPOSE $PORT

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost:${PORT}/ || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5000", "--workers", "4"]