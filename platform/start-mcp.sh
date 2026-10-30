#!/bin/zsh
set -eu
cd "${0:A:h}"
export QUNKONG_TOKEN_FILE="${QUNKONG_TOKEN_FILE:-$PWD/.state/admin-token}"
exec ../.venv/bin/python -m backend.mcp_server
