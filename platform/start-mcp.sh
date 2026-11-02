#!/bin/zsh
set -eu
cd "${0:A:h}"
export PHONEUSE_TOKEN_FILE="${PHONEUSE_TOKEN_FILE:-${QUNKONG_TOKEN_FILE:-${PHONEUSE_STATE_DIR:-${QUNKONG_STATE_DIR:-$PWD/.state}}/admin-token}}"
exec ../.venv/bin/python -m backend.mcp_server
