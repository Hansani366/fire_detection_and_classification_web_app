FROM python:3.11-slim

# Build arg to select backend — must match VLM_BACKEND in docker-compose.yml
ARG VLM_BACKEND=gemini

RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Only install Ollama when building for moondream
RUN if [ "$VLM_BACKEND" = "moondream" ]; then \
        apt-get update && apt-get install -y unzip tar wget git zstd \
        && rm -rf /var/lib/apt/lists/* \
        && curl -fsSL https://ollama.com/install.sh | sh; \
    else \
        echo "Gemini backend selected — skipping Ollama install."; \
    fi

COPY moondream_api.py .
COPY entrypoint.sh .
RUN chmod +x /app/entrypoint.sh

EXPOSE 8019

CMD ["/app/entrypoint.sh"]