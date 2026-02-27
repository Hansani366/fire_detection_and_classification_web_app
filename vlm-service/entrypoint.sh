#!/bin/bash
set -e

echo "═══════════════════════════════════"
echo "  FireWatch VLM Service Starting   "
echo "  Backend: ${VLM_BACKEND:-gemini}  "
echo "═══════════════════════════════════"

if [ "${VLM_BACKEND:-gemini}" = "moondream" ]; then
    echo "[1/3] Starting Ollama server..."
    ollama serve &

    echo "[2/3] Waiting for Ollama to be ready..."
    for i in $(seq 1 30); do
        if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
            echo "Ollama is ready."
            break
        fi
        echo "  Attempt $i/30..."
        sleep 2
    done

    echo "[3/3] Pulling Moondream model (if not already present)..."
    ollama pull moondream:latest || echo "Warning: moondream pull failed, may already exist."
else
    echo "[Gemini mode] Skipping Ollama and Moondream setup."
fi

echo "Starting FastAPI on port 8019..."
uvicorn moondream_api:app --host 0.0.0.0 --port 8019