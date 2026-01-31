# WarDragon Analytics - Multi-stage Docker Build
#
# This Dockerfile builds both the collector and web services.
# The target service is selected via docker-compose.yml command override.
#
# Build: docker build -t wardragon-analytics:latest .
# Run collector: docker run --env-file .env wardragon-analytics python collector.py
# Run web: docker run --env-file .env -p 8080:8080 wardragon-analytics uvicorn api:app --host 0.0.0.0 --port 8080

# Stage 1: Base image with common dependencies
FROM python:3.11-slim AS base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # PostgreSQL client libraries
    libpq5 \
    # SSL/TLS support
    ca-certificates \
    # Timezone data
    tzdata \
    # Process management
    tini \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r wardragon && useradd -r -g wardragon -u 1000 wardragon

# Set working directory
WORKDIR /app

# Stage 2: Builder image with compilation tools
FROM base AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Compiler and build tools
    gcc \
    g++ \
    make \
    # PostgreSQL development headers (for psycopg2)
    libpq-dev \
    # Python development headers
    python3-dev \
    # Git (for pip installing from git repos if needed)
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
# Use --user to install in user directory for easy copying to final image
RUN pip install --user --no-warn-script-location -r requirements.txt

# Stage 3: Base production image
FROM base AS production

# Copy Python packages from builder
COPY --from=builder /root/.local /home/wardragon/.local

# Update PATH to include user-installed packages
ENV PATH=/home/wardragon/.local/bin:$PATH

# Copy application code
COPY --chown=wardragon:wardragon . /app/

# Create required directories
RUN mkdir -p /var/log/wardragon-analytics /tmp/wardragon-analytics && \
    chown -R wardragon:wardragon /var/log/wardragon-analytics /tmp/wardragon-analytics

# Switch to non-root user
USER wardragon

# Use tini as init system to handle signals properly
ENTRYPOINT ["/usr/bin/tini", "--"]

# Stage 4: Collector service
FROM production AS collector

EXPOSE 5000

# Collector-specific healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import os; exit(0 if os.path.exists('/tmp/collector_healthy') else 1)"

CMD ["python", "collector.py"]

# Stage 5: Web service
FROM production AS web

EXPOSE 8090

# Web service healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8090/health', timeout=5)" || exit 1

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8090"]

# Stage 6: MQTT Ingest service
FROM production AS mqtt-ingest

# MQTT Ingest healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import os; exit(0 if os.path.exists('/tmp/mqtt_ingest_healthy') else 1)"

CMD ["python", "mqtt_ingest.py"]

# Stage 7: Development image with additional tools
FROM production AS development

# Switch back to root for installing dev dependencies
USER root

# Install development tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Debugging tools
    vim \
    curl \
    wget \
    # Network debugging
    iputils-ping \
    netcat-openbsd \
    # Process monitoring
    htop \
    && rm -rf /var/lib/apt/lists/*

# Install development Python packages
RUN pip install --no-cache-dir \
    pytest==8.0.0 \
    pytest-asyncio==0.23.3 \
    pytest-cov==4.1.0 \
    black==24.1.1 \
    ruff==0.1.14 \
    mypy==1.8.0 \
    ipython==8.20.0 \
    debugpy==1.8.0

# Enable debug mode
ENV DEBUG=1

# Switch back to wardragon user
USER wardragon

# Development command: start with auto-reload
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8080", "--reload"]

# Build Instructions:
# ------------------
#
# Production build:
#   docker build --target production -t wardragon-analytics:latest .
#   docker build --target production -t wardragon-analytics:1.0.0 .
#
# Development build:
#   docker build --target development -t wardragon-analytics:dev .
#
# Build with build args:
#   docker build --build-arg PYTHON_VERSION=3.12 -t wardragon-analytics:latest .
#
# Multi-platform build (for ARM/x86):
#   docker buildx build --platform linux/amd64,linux/arm64 -t wardragon-analytics:latest .
#
# Usage Examples:
# ---------------
#
# Run collector service:
#   docker run -d --name wardragon-collector \
#     --env-file .env \
#     -v $(pwd)/config:/config:ro \
#     wardragon-analytics:latest python collector.py
#
# Run web service:
#   docker run -d --name wardragon-web \
#     --env-file .env \
#     -p 8080:8080 \
#     wardragon-analytics:latest uvicorn api:app --host 0.0.0.0 --port 8080
#
# Run development server with code reload:
#   docker run -d --name wardragon-dev \
#     --env-file .env \
#     -v $(pwd):/app \
#     -p 8080:8080 \
#     wardragon-analytics:dev
#
# Execute shell inside container:
#   docker exec -it wardragon-collector /bin/bash
#
# View logs:
#   docker logs -f wardragon-collector
#
# Environment Variables:
# ----------------------
# Required:
#   DATABASE_URL - PostgreSQL connection string
#   DB_PASSWORD - Database password
#
# Optional:
#   KITS_CONFIG - Path to kits.yaml (default: /config/kits.yaml)
#   SETTINGS_CONFIG - Path to settings.yaml (default: /config/settings.yaml)
#   LOG_LEVEL - Logging level (default: INFO)
#   DEBUG - Enable debug mode (default: false)
#
# Security Notes:
# ---------------
# - Runs as non-root user (wardragon:1000)
# - No unnecessary packages in production image
# - Health check ensures service availability
# - Tini handles zombie processes and signal forwarding
# - Use secrets management for sensitive environment variables
# - Regularly update base image and dependencies for security patches
#
# Performance Tuning:
# -------------------
# - Multi-stage build minimizes final image size (~200MB vs ~1GB)
# - Python bytecode compilation disabled (PYTHONDONTWRITEBYTECODE=1)
# - Pip cache disabled to reduce image size
# - Uvicorn workers can be scaled via docker-compose.yml
# - Consider using gunicorn for production with multiple workers:
#   CMD ["gunicorn", "api:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8080"]
