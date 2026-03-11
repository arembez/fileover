# Dockerfile
# Copyright: (c) 2026, Alex Rembez (@arembez) <arembez@gmail.com>
# MIT License (see LICENSE or https://opensource.org/licenses/MIT)

FROM python:3.11-slim

# Set the working directory to /fileover
WORKDIR /fileover

# Install system dependencies (if needed for building packages)
RUN apt-get update && apt-get install -y gcc && rm -rf /var/lib/apt/lists/*

# Copy and install main dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code to /fileover/app
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