#!/bin/bash

echo "Starting Ollama..."
ollama serve &

# Wait for Ollama to start
sleep 5

echo "Pulling Moondream model if not present..."
ollama pull moondream:latest

echo "Starting FastAPI..."
uvicorn moondream_api:app --host 0.0.0.0 --port 8019