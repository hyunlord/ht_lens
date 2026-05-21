#!/usr/bin/env bash
# Dev convenience: start/stop/status/logs for ht-lens serve in background.
# Usage:
#   scripts/dev_serve.sh start [--port N] [--db PATH]
#   scripts/dev_serve.sh stop
#   scripts/dev_serve.sh status
#   scripts/dev_serve.sh logs [-f]
#   scripts/dev_serve.sh restart
#
# State:
#   PID file:  ~/.ht_lens/server.pid
#   Log file:  ~/.ht_lens/server.log
#
# Default port 8080, host 0.0.0.0, db data/ht_lens.db (relative to repo root).
# This is NOT a production deployment script — single-user, no auth, tailscale-only.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="${HT_LENS_STATE_DIR:-$HOME/.ht_lens}"
PID_FILE="$STATE_DIR/server.pid"
LOG_FILE="$STATE_DIR/server.log"

mkdir -p "$STATE_DIR"

cmd="${1:-status}"
shift || true

# default opts
PORT=8080
HOST=0.0.0.0
DB="$REPO_ROOT/data/ht_lens.db"
FOLLOW=0

# parse options
while [[ $# -gt 0 ]]; do
  case "$1" in
    --port)  PORT="$2"; shift 2 ;;
    --host)  HOST="$2"; shift 2 ;;
    --db)    DB="$2"; shift 2 ;;
    -f)      FOLLOW=1; shift ;;
    *)       shift ;;
  esac
done

is_running() {
  [[ -f "$PID_FILE" ]] || return 1
  local pid
  pid="$(cat "$PID_FILE" 2>/dev/null || echo)"
  [[ -n "$pid" ]] || return 1
  kill -0 "$pid" 2>/dev/null
}

case "$cmd" in
  start)
    if is_running; then
      echo "already running (pid $(cat "$PID_FILE"))"
      exit 0
    fi
    cd "$REPO_ROOT"
    # quick port-occupancy check
    if ss -tlnp 2>/dev/null | grep -q ":$PORT "; then
      echo "port $PORT already in use" >&2
      exit 2
    fi
    echo "starting ht-lens serve on $HOST:$PORT (db=$DB)..."
    nohup uv run ht-lens serve --host "$HOST" --port "$PORT" --db "$DB" \
      > "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    sleep 2
    if is_running; then
      echo "started (pid $(cat "$PID_FILE"))"
      echo "log: $LOG_FILE"
    else
      echo "failed to start. tail -20 $LOG_FILE:" >&2
      tail -20 "$LOG_FILE" >&2 || true
      rm -f "$PID_FILE"
      exit 1
    fi
    ;;
  stop)
    if is_running; then
      pid="$(cat "$PID_FILE")"
      echo "stopping pid $pid..."
      kill "$pid"
      for _ in 1 2 3 4 5; do
        kill -0 "$pid" 2>/dev/null || break
        sleep 1
      done
      if kill -0 "$pid" 2>/dev/null; then
        echo "force killing pid $pid"
        kill -9 "$pid" || true
      fi
      rm -f "$PID_FILE"
      echo "stopped"
    else
      echo "not running"
      rm -f "$PID_FILE"
    fi
    ;;
  status)
    if is_running; then
      pid="$(cat "$PID_FILE")"
      echo "running (pid $pid)"
      ps -o pid,etime,rss,cmd -p "$pid" 2>/dev/null || true
    else
      echo "not running"
    fi
    ;;
  logs)
    if [[ "$FOLLOW" == "1" ]]; then
      tail -f "$LOG_FILE"
    else
      tail -100 "$LOG_FILE"
    fi
    ;;
  restart)
    "$0" stop || true
    sleep 1
    "$0" start
    ;;
  *)
    echo "usage: $0 {start|stop|status|logs [-f]|restart} [--port N] [--host H] [--db PATH]" >&2
    exit 2
    ;;
esac
