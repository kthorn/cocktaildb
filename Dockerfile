# Dockerfile for CocktailDB FastAPI application

FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY api/ ./api/
COPY schema-deploy/schema.sql ./schema.sql

# Create database directory
RUN mkdir -p /data

# Set environment variables
ENV PYTHONPATH=/app
ENV DB_PATH=/data/cocktaildb.db
ENV ENVIRONMENT=dev

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["python", "-m", "api.main"]