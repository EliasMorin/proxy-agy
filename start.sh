#!/usr/bin/env bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

PID_FILE="$DIR/proxy.pid"
LOG_FILE="$DIR/proxy.log"

start_daemon() {
    if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
        echo "⚠️  Proxy server is already running with PID $(cat "$PID_FILE")."
        exit 0
    fi
    echo "🚀 Starting Antigravity CLI OpenAI Proxy in background..."
    nohup python3 main.py "$@" > "$LOG_FILE" 2>&1 &
    PID=$!
    echo $PID > "$PID_FILE"
    sleep 1
    if kill -0 $PID 2>/dev/null; then
        echo "✅ Proxy server started successfully (PID: $PID)."
        echo "📄 Logs: $LOG_FILE"
        echo "📍 URL:  http://127.0.0.1:8000"
    else
        echo "❌ Failed to start proxy server. Check $LOG_FILE for details."
        exit 1
    fi
}

stop_daemon() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 $PID 2>/dev/null; then
            echo "🛑 Stopping proxy server (PID: $PID)..."
            kill $PID
            rm -f "$PID_FILE"
            echo "✅ Server stopped."
        else
            echo "⚠️  Process $PID is not running. Removing stale PID file."
            rm -f "$PID_FILE"
        fi
    else
        # Fallback search for running main.py
        PIDS=$(pgrep -f "python3.*main.py" || true)
        if [ -n "$PIDS" ]; then
            echo "🛑 Stopping running proxy processes ($PIDS)..."
            kill $PIDS
            echo "✅ Server stopped."
        else
            echo "ℹ️  No proxy server running."
        fi
    fi
}

status_daemon() {
    if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
        echo "✅ Proxy server is running (PID: $(cat "$PID_FILE"))."
        echo "📍 Base URL: http://127.0.0.1:8000/v1"
    else
        PIDS=$(pgrep -f "python3.*main.py" || true)
        if [ -n "$PIDS" ]; then
            echo "✅ Proxy server is running (PIDs: $PIDS)."
        else
            echo "⚪ Proxy server is stopped."
        fi
    fi
}

case "$1" in
    start)
        shift
        start_daemon "$@"
        ;;
    stop)
        stop_daemon
        ;;
    restart)
        shift
        stop_daemon
        sleep 1
        start_daemon "$@"
        ;;
    status)
        status_daemon
        ;;
    logs)
        tail -f "$LOG_FILE"
        ;;
    login)
        python3 main.py --login
        ;;
    check-auth)
        python3 main.py --check-auth
        ;;
    *)
        # Default foreground run
        echo "🚀 Running Antigravity CLI OpenAI Proxy in foreground..."
        echo "Tip: Run './start.sh start' to run in background, or './start.sh stop' to stop."
        python3 main.py "$@"
        ;;
esac
