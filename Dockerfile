# Build stage
FROM python:3.8-slim AS builder

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libsqlite3-dev \
    libssl-dev \
    zlib1g-dev \
    libbz2-dev \
    libreadline-dev \
    libffi-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies and Gunicorn
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Runtime stage
FROM python:3.8-slim

# Install runtime dependencies and networking tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libsqlite3-0 \
    curl \
    iputils-ping \
    net-tools \
    netcat-traditional \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Copy installed packages and binaries from builder
COPY --from=builder /usr/local/lib/python3.8/site-packages /usr/local/lib/python3.8/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY . .

# Set environment variables
ENV FLASK_APP=main.py
ENV FLASK_RUN_HOST=0.0.0.0
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8082

# Run the application with Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8082", "--workers", "4", "main:app"]
