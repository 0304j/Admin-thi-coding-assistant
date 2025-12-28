# Multi-stage build for production
FROM python:3.11-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create wheel directory
WORKDIR /wheels

# Copy requirements and build wheels
COPY Model_manager/requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /wheels -r requirements.txt

# Production stage
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV FLASK_APP=vue-api-server.py
ENV FLASK_ENV=production

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY Model_manager/requirements.txt .

# Copy wheels from builder stage and install
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links /wheels --force-reinstall -r requirements.txt || \
    pip install --no-cache-dir -r requirements.txt
RUN rm -rf /wheels

# Copy application files from Model_manager
COPY Model_manager/vue-api-server.py .
COPY Model_manager/vue-model-manager.html .
COPY Model_manager/k8s_client.py .

# Create non-root user for security
RUN adduser --disabled-password --gecos '' appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/api/health || exit 1

# Start with Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--worker-class", "sync", "--timeout", "60", "--access-logfile", "-", "--error-logfile", "-", "vue-api-server:app"]