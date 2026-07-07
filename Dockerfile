# Dockerfile
# Copyright: (c) 2026, Alex Rembez (@arembez) <arembez@gmail.com>
# MIT License (see LICENSE or https://opensource.org/licenses/MIT)

FROM python:3.14.3-slim-trixie AS builder

# Install build dependencies (gcc, headers, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    libffi-dev \
    libssl-dev \
    pkg-config \
    autoconf \
    automake \
    libtool \
    m4 \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /build

# Copy requirements first (for better caching)
COPY requirements.txt .

# Install Python packages (will compile C extensions)
RUN pip install --no-cache-dir --user -r requirements.txt

# Final stage
FROM python:3.14.3-slim-trixie

# Set the working directory to /fileover
WORKDIR /fileover

# Install only runtime system dependencies (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /root/.local /root/.local

# Make scripts from .local/bin available
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY ./app /fileover/app

# Copy healthcheck script and make it executable
COPY healthcheck.py /fileover/healthcheck.py
RUN chmod +x /fileover/healthcheck.py

# Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Configure environment
ENV PYTHONPATH=/fileover
ENV PYTHONUNBUFFERED=1

# Open port
EXPOSE 8435

# Add healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD /fileover/healthcheck.py

# Run entrypoint
ENTRYPOINT ["/entrypoint.sh"]