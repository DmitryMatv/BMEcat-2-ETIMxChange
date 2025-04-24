FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create templates directory if it doesn't exist
RUN mkdir -p templates

# Create a non-root user to run the app
RUN adduser --disabled-password --gecos '' appuser
USER appuser

EXPOSE 5000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5000", "--workers", "2"]