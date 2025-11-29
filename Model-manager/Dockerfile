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
COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /wheels -r requirements.txt

# Production stage
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV FLASK_APP=app.py
ENV FLASK_ENV=production

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy wheels from builder stage and clean up
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links /wheels --force-reinstall -r requirements.txt || \
    pip install --no-cache-dir -r requirements.txt
RUN rm -rf /wheels

# Copy application files
COPY app.py .
COPY config.py .
COPY vue-model-manager.html ./
COPY k8s_client.py .
COPY hf_models.py .

# Copy route modules
COPY routes/ ./routes/
COPY utils/ ./utils/

# Create non-root user for security
RUN adduser --disabled-password --gecos '' appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expose port (updated for enhanced API server)
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/api/health || exit 1

# Start with Gunicorn (production WSGI server) instead of Flask development server
# This provides better memory management and resource handling
ENV FLASK_ENV=production
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--worker-class", "sync", "--timeout", "60", "--access-logfile", "-", "--error-logfile", "-", "app:app"]
