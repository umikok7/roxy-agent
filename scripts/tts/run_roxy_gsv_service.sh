#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/artifacts/gpt-sovits-roxy/.venv"

if [ ! -x "$VENV/bin/python" ]; then
  echo "Missing virtualenv: $VENV"
  exit 1
fi

# ── Required env vars ────────────────────────────────────────────────────────
: "${ROXY_GSV_DEPLOY_ROOT:?Please set ROXY_GSV_DEPLOY_ROOT (e.g. /path/to/gpt-sovits-roxy)}"
: "${ROXY_GSV_T2S_WEIGHTS:?Please set ROXY_GSV_T2S_WEIGHTS (e.g. /path/to/YourChar.ckpt)}"
: "${ROXY_GSV_VITS_WEIGHTS:?Please set ROXY_GSV_VITS_WEIGHTS (e.g. /path/to/YourChar.pth)}"
: "${ROXY_GSV_REF_AUDIO:?Please set ROXY_GSV_REF_AUDIO (e.g. /path/to/reference.wav)}"

exec "$VENV/bin/python" "$ROOT/scripts/tts/roxy_gsv_service.py"