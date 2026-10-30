#!/bin/zsh
set -eu
cd "${0:A:h}"
exec ../.venv/bin/python -m uvicorn backend.api:app --host 127.0.0.1 --port 8765 --ws-max-size 4096 --ws-per-message-deflate false
