FROM python:3.11-slim

WORKDIR /app

# Environment variables (passed from docker-compose build args)
ARG KB_API_PORT=8000
ENV KB_API_PORT=${KB_API_PORT}

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY kbapi.py .

# Expose port
EXPOSE ${KB_API_PORT}

# Startup command (will be overridden by docker-compose)
CMD uvicorn kbapi:app --host 0.0.0.0 --port ${KB_API_PORT}