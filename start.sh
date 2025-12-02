#!/usr/bin/env bash

# Change to project directory (optional — adjust as needed)
PROJECT_ROOT="$(dirname "$0")"
cd "$PROJECT_ROOT"

# Activate virtual environment (optional — uncomment if you use one)
source .venv/bin/activate

# Start the FastAPI backend in background
echo "Starting FastAPI (uvicorn) on port 8000..."
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload &  # & means run in background
UVICORN_PID=$!

# Wait a little for server to spin up (optional)
sleep 2

# Start the Streamlit UI
echo "Starting Streamlit UI..."
uv run streamlit run app.py &  # also run in background
STREAMLIT_PID=$!

# Function to handle cleanup on exit
cleanup() {
  echo "Shutting down..."
  kill $UVICORN_PID
  kill $STREAMLIT_PID
  exit 0
}

# Trap ctrl-C (SIGINT) or script termination to cleanup child processes
trap cleanup SIGINT SIGTERM

echo "Both servers running. Uvicorn PID=$UVICORN_PID, Streamlit PID=$STREAMLIT_PID"
echo "Press Ctrl-C to stop."

# Wait indefinitely (so script doesn't exit immediately)
while true; do
  sleep 1
done