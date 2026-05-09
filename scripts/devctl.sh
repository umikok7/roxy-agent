#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${ROOT_DIR}/.runtime"
LOG_DIR="${RUNTIME_DIR}/logs"
PID_DIR="${RUNTIME_DIR}/pids"
COMPOSE_FILE="${ROOT_DIR}/docker-compose.yml"

mkdir -p "${LOG_DIR}" "${PID_DIR}"

BACKEND_PID_FILE="${PID_DIR}/backend.pid"
FRONTEND_PID_FILE="${PID_DIR}/frontend.pid"
DESKTOP_PID_FILE="${PID_DIR}/desktop.pid"

BACKEND_LOG_FILE="${LOG_DIR}/backend.log"
FRONTEND_LOG_FILE="${LOG_DIR}/frontend.log"
DESKTOP_LOG_FILE="${LOG_DIR}/desktop.log"

info() {
  printf '[devctl] %s\n' "$*"
}

warn() {
  printf '[devctl] %s\n' "$*" >&2
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    warn "Missing required command: $1"
    exit 1
  fi
}

pid_is_running() {
  local pid="$1"
  kill -0 "${pid}" >/dev/null 2>&1
}

process_group_is_running() {
  local pid="$1"
  kill -0 -- "-${pid}" >/dev/null 2>&1
}

read_pid() {
  local pid_file="$1"
  if [[ -f "${pid_file}" ]]; then
    tr -d '[:space:]' < "${pid_file}"
  fi
}

cleanup_pid_file_if_stale() {
  local pid_file="$1"
  local pid
  pid="$(read_pid "${pid_file}")"
  if [[ -n "${pid}" ]] && ! pid_is_running "${pid}"; then
    rm -f "${pid_file}"
  fi
}

is_service_running() {
  local pid_file="$1"
  cleanup_pid_file_if_stale "${pid_file}"
  local pid
  pid="$(read_pid "${pid_file}")"
  [[ -n "${pid}" ]] && pid_is_running "${pid}"
}

start_background_service() {
  local name="$1"
  local workdir="$2"
  local command="$3"
  local pid_file="$4"
  local log_file="$5"

  if is_service_running "${pid_file}"; then
    info "${name} is already running (pid $(read_pid "${pid_file}"))"
    return 0
  fi

  info "Starting ${name}..."
  require_command python3
  SERVICE_NAME="${name}" \
  SERVICE_WORKDIR="${workdir}" \
  SERVICE_COMMAND="${command}" \
  SERVICE_LOG_FILE="${log_file}" \
    python3 - <<'PY' >"${pid_file}"
import os
import subprocess

with open(os.environ["SERVICE_LOG_FILE"], "ab", buffering=0) as log_file:
    process = subprocess.Popen(
        ["bash", "-lc", os.environ["SERVICE_COMMAND"]],
        cwd=os.environ["SERVICE_WORKDIR"],
        stdin=subprocess.DEVNULL,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    print(process.pid)
PY

  sleep 1

  if ! is_service_running "${pid_file}"; then
    warn "Failed to start ${name}. Check ${log_file}"
    return 1
  fi

  info "${name} started (pid $(read_pid "${pid_file}"))"
}

stop_background_service() {
  local name="$1"
  local pid_file="$2"

  cleanup_pid_file_if_stale "${pid_file}"
  local pid
  pid="$(read_pid "${pid_file}")"

  if [[ -z "${pid}" ]]; then
    info "${name} is not running"
    return 0
  fi

  info "Stopping ${name} (pid ${pid})..."
  kill -TERM -- "-${pid}" >/dev/null 2>&1 || kill "${pid}" >/dev/null 2>&1 || true

  for _ in $(seq 1 20); do
    if ! pid_is_running "${pid}" && ! process_group_is_running "${pid}"; then
      rm -f "${pid_file}"
      info "${name} stopped"
      return 0
    fi
    sleep 0.5
  done

  warn "${name} did not stop gracefully, sending SIGKILL"
  kill -KILL -- "-${pid}" >/dev/null 2>&1 || kill -9 "${pid}" >/dev/null 2>&1 || true
  rm -f "${pid_file}"
}

start_qdrant() {
  require_command docker
  docker compose -f "${COMPOSE_FILE}" up -d qdrant >/dev/null
  info "qdrant is up via docker compose"
}

stop_qdrant() {
  require_command docker
  docker compose -f "${COMPOSE_FILE}" stop qdrant >/dev/null || true
  info "qdrant stopped"
}

backend_command() {
  if [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
    printf '%q ' "${ROOT_DIR}/.venv/bin/python" -m uvicorn APP.api.app:create_app --factory --reload --host 0.0.0.0 --port 8000
  elif command -v uv >/dev/null 2>&1; then
    printf '%q ' uv run python -m uvicorn APP.api.app:create_app --factory --reload --host 0.0.0.0 --port 8000
  else
    warn "Neither .venv/bin/python nor uv is available for backend startup"
    exit 1
  fi
}

start_backend() {
  start_background_service "backend" "${ROOT_DIR}" "$(backend_command)" "${BACKEND_PID_FILE}" "${BACKEND_LOG_FILE}"
}

start_frontend() {
  require_command npm
  start_background_service "frontend" "${ROOT_DIR}/frontend" "npm run dev" "${FRONTEND_PID_FILE}" "${FRONTEND_LOG_FILE}"
}

start_desktop() {
  require_command npm
  start_background_service "desktop" "${ROOT_DIR}/desktop" "npm run dev" "${DESKTOP_PID_FILE}" "${DESKTOP_LOG_FILE}"
}

stop_backend() {
  stop_background_service "backend" "${BACKEND_PID_FILE}"
}

stop_frontend() {
  stop_background_service "frontend" "${FRONTEND_PID_FILE}"
}

stop_desktop() {
  stop_background_service "desktop" "${DESKTOP_PID_FILE}"
}

status_line() {
  local name="$1"
  local pid_file="$2"
  if is_service_running "${pid_file}"; then
    printf '%-10s running (pid %s)\n' "${name}" "$(read_pid "${pid_file}")"
  else
    printf '%-10s stopped\n' "${name}"
  fi
}

status_qdrant() {
  require_command docker
  local container_id
  container_id="$(docker compose -f "${COMPOSE_FILE}" ps -q qdrant)"
  if [[ -n "${container_id}" ]] && docker ps -q --no-trunc | grep -q "${container_id}"; then
    printf '%-10s running (container %s)\n' "qdrant" "${container_id:0:12}"
  else
    printf '%-10s stopped\n' "qdrant"
  fi
}

health_backend() {
  if command -v curl >/dev/null 2>&1 && curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
    printf '%-10s healthy (%s)\n' "backend" "http://127.0.0.1:8000/health"
  else
    printf '%-10s unavailable\n' "backend"
  fi
}

health_frontend() {
  if command -v curl >/dev/null 2>&1 && curl -fsS http://127.0.0.1:3000 >/dev/null 2>&1; then
    printf '%-10s healthy (%s)\n' "frontend" "http://127.0.0.1:3000"
  else
    printf '%-10s unavailable\n' "frontend"
  fi
}

health_qdrant() {
  if command -v curl >/dev/null 2>&1 && curl -fsS http://127.0.0.1:6333/collections >/dev/null 2>&1; then
    printf '%-10s healthy (%s)\n' "qdrant" "http://127.0.0.1:6333"
  else
    printf '%-10s unavailable\n' "qdrant"
  fi
}

logs_service() {
  local name="$1"
  local lines="${2:-50}"
  local log_file
  case "${name}" in
    backend) log_file="${BACKEND_LOG_FILE}" ;;
    frontend) log_file="${FRONTEND_LOG_FILE}" ;;
    desktop) log_file="${DESKTOP_LOG_FILE}" ;;
    *)
      warn "Unknown service: ${name}. Expected backend, frontend, or desktop."
      exit 1
      ;;
  esac

  if [[ ! -f "${log_file}" ]]; then
    warn "No log file found for ${name}"
    exit 1
  fi

  tail -n "${lines}" "${log_file}"
}

bootstrap() {
  if command -v uv >/dev/null 2>&1; then
    info "Installing Python dependencies with uv sync"
    (cd "${ROOT_DIR}" && uv sync)
  else
    warn "uv is not installed; skipping Python dependency bootstrap"
  fi

  require_command npm
  info "Installing frontend dependencies"
  (cd "${ROOT_DIR}/frontend" && npm install)
  info "Installing desktop dependencies"
  (cd "${ROOT_DIR}/desktop" && npm install)
}

up() {
  start_qdrant
  start_backend
  start_frontend
  start_desktop
  info "All services requested. Run 'make status' or 'make health' to inspect."
}

down() {
  stop_desktop
  stop_frontend
  stop_backend
  stop_qdrant
}

restart() {
  down
  up
}

status() {
  status_qdrant
  status_line "backend" "${BACKEND_PID_FILE}"
  status_line "frontend" "${FRONTEND_PID_FILE}"
  status_line "desktop" "${DESKTOP_PID_FILE}"
}

health() {
  health_qdrant
  health_backend
  health_frontend
  if is_service_running "${DESKTOP_PID_FILE}"; then
    printf '%-10s running\n' "desktop"
  else
    printf '%-10s unavailable\n' "desktop"
  fi
}

reindex_kb() {
  if [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
    (cd "${ROOT_DIR}" && "${ROOT_DIR}/.venv/bin/python" APP/main.py reindex-kb)
  elif command -v uv >/dev/null 2>&1; then
    (cd "${ROOT_DIR}" && uv run python APP/main.py reindex-kb)
  else
    warn "Neither .venv/bin/python nor uv is available for reindex"
    exit 1
  fi
}

usage() {
  cat <<'EOF'
Usage: scripts/devctl.sh <command> [args]

Commands:
  bootstrap             Install backend/frontend/desktop dependencies
  up                    Start qdrant, backend, frontend, desktop
  down                  Stop qdrant, backend, frontend, desktop
  restart               Restart all services
  status                Show process/container status
  health                Check service health endpoints where available
  logs <service> [n]    Tail backend/frontend/desktop log file
  reindex-kb            Rebuild the knowledge base index
EOF
}

main() {
  local command="${1:-help}"
  shift || true

  case "${command}" in
    bootstrap) bootstrap ;;
    up) up ;;
    down) down ;;
    restart) restart ;;
    status) status ;;
    health) health ;;
    logs) logs_service "${1:-}" "${2:-50}" ;;
    reindex-kb) reindex_kb ;;
    help|-h|--help) usage ;;
    *)
      warn "Unknown command: ${command}"
      usage
      exit 1
      ;;
  esac
}

main "$@"
