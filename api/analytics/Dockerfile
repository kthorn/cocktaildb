FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Layer 1: Install barcart dependencies (heavy, rarely change)
COPY packages/barcart/requirements.txt /tmp/barcart-requirements.txt
RUN uv pip install --system --no-cache -r /tmp/barcart-requirements.txt

# Layer 2: Install analytics dependencies (rarely change)
COPY api/analytics/requirements.txt /tmp/analytics-requirements.txt
RUN uv pip install --system --no-cache -r /tmp/analytics-requirements.txt

# Layer 3: Copy shared modules (change occasionally)
COPY api/db/ /app/db/
COPY api/utils/ /app/utils/
COPY api/core/ /app/core/

# Layer 4: Install barcart package code (changes frequently)
COPY packages/barcart/ /app/packages/barcart/
RUN uv pip install --system --no-deps /app/packages/barcart/

# Layer 5: Copy analytics module (changes frequently)
COPY api/analytics/ /app/analytics/

# Set PYTHONPATH so imports work
ENV PYTHONPATH=/app

# Run the analytics module
CMD ["python", "-m", "analytics.analytics_refresh"]
