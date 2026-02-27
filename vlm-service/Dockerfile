# Use lightweight Python image
FROM python:3.11-slim

# Install dependencies
RUN apt-get update && apt-get install -y \
    curl \
    unzip \
    tar \
    wget \
    git \
    zstd \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy code and requirements
COPY moondream_api.py requirements.txt /app/

# Install Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Install Ollama
RUN curl -fsSL https://ollama.com/install.sh | sh

# Copy entrypoint script
COPY entrypoint.sh /app/
RUN chmod +x /app/entrypoint.sh

# Expose API port
EXPOSE 8019

# Run entrypoint
CMD ["/app/entrypoint.sh"]