FROM python:3.13-slim

WORKDIR /app

# Create a non-root user earlier in the process
RUN adduser --disabled-password --gecos '' appuser

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Create templates directory with proper ownership
RUN mkdir -p templates && chown -R appuser:appuser /app

# Copy application files and fix permissions
COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 5000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5000", "--workers", "2"]