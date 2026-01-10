#!/bin/bash

# Set the port for the application
PORT=9090

# Check if port is already in use and kill the process
echo "Checking if port $PORT is already in use..."
PID=$(lsof -t -i:$PORT)

if [ -n "$PID" ]; then
  echo "Port $PORT is in use by PID(s): $PID"
  echo "Killing process(es)..."
  kill -9 $PID
  echo "Port $PORT freed."
fi

# Start the OmniBioAI Toolserver on port 9090 using uvicorn
echo "Starting OmniBioAI Toolserver on port $PORT..."
APP_FACTORY="toolserver_app:create_app"
exec uvicorn "$APP_FACTORY" --factory --host 0.0.0.0 --port "$PORT" --log-level info
