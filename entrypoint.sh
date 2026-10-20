#!/bin/bash

# Start the Ollama server in the background
ollama serve &

# Wait for the server to be ready using the built-in 'ollama list' command
echo "Waiting for Ollama server to start..."
while ! ollama list > /dev/null 2>&1; do
  sleep 2
done

# If TEST_MODEL was not passed via Docker environment, read it directly from mounted /root/.env
if [ -z "$TEST_MODEL" ] && [ -f /root/.env ]; then
  echo "Reading TEST_MODEL from /root/.env..."
  TEST_MODEL=$(grep -E '^TEST_MODEL=' /root/.env | cut -d'=' -f2- | tr -d '\r"' | xargs)
fi

# Fallback default if still not set
MODEL="${TEST_MODEL:-llama3.2}"
MODEL=$(echo "$MODEL" | tr -d '[:space:]\r"')

# Enforce: exactly 1 model per container (no CSV accepted)
if echo "$MODEL" | grep -q ","; then
  echo "=========================================="
  echo "ERROR: Multiple models (CSV) detected in TEST_MODEL: '$MODEL'"
  echo "Each model must live in its own container. Please specify only 1 model in .env."
  echo "=========================================="
  exit 1
fi

echo "=========================================="
echo "Initializing single model for this container: $MODEL"
echo "=========================================="

# 1. Pull the base model
echo "Pulling model: $MODEL..."
ollama pull "$MODEL"

# 2. Configure model with num_ctx=8192
echo "Configuring model $MODEL with num_ctx=8192..."
cat <<EOF > /tmp/Modelfile
FROM $MODEL
PARAMETER num_ctx 8192
EOF
ollama create "$MODEL" -f /tmp/Modelfile > /dev/null 2>&1
rm -f /tmp/Modelfile

# 3. Start model in GPU memory and run warm-up pass (num_ctx=8192)
echo "Warming up model $MODEL in GPU memory (num_ctx=8192, SWA buffers & computation graph)..."
ollama run "$MODEL" "Warmup initialization: verify inference pipeline, Sliding Window Attention buffers, and computation graphs are ready." > /dev/null 2>&1


echo "=========================================="
echo "Model initialization complete!"
echo "Model parameters:"
ollama show --parameters "$MODEL" | grep "num_ctx"
echo "------------------------------------------"
echo "Active models in GPU memory (ollama ps):"
ollama ps
echo "=========================================="

# Keep the container alive
wait