#!/bin/bash
PORT=$1
CUSTOM_HOME=$2
if [ -z "$PORT" ] || [ -z "$CUSTOM_HOME" ]; then
  echo "Usage: ./start_proxy.sh <PORT> <CUSTOM_HOME>"
  exit 1
fi
mkdir -p "$CUSTOM_HOME"
export HOME="$CUSTOM_HOME"
export HOST="0.0.0.0"
export PORT="$PORT"
cd /opt/proxy-agy
source venv/bin/activate
exec python3 main.py
