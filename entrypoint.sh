#!/bin/bash

# Start the Ollama server in the background
ollama serve &

# Wait for the server to be ready using the built-in 'ollama list' command
echo "Waiting for Ollama server to start..."
while ! ollama list > /dev/null 2>&1; do
  sleep 2
done

# Pull the model (idempotent: won't re-download if it already exists)
echo "Checking/Pulling Llama model..."
ollama pull llama3.2

# Keep the container alive
wait