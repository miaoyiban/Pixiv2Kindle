FROM python:3.11-slim

WORKDIR /app

# Install system deps (needed by lxml/ebooklib).
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libxml2-dev libxslt1-dev && \
    rm -rf /var/lib/apt/lists/*

# Install Python deps.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code.
COPY packages/ packages/
COPY apps/ apps/
COPY pyproject.toml .

# Install project in editable mode so imports work.
RUN pip install --no-cache-dir -e .

# Create temp dir.
RUN mkdir -p /app/tmp

# Expose port.
EXPOSE 8080

# Run with uvicorn.
CMD ["uvicorn", "apps.api_server.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
