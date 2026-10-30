#!/bin/zsh
set -eu
cd "${0:A:h}"
command -v python3.13 >/dev/null || { echo 'Install Python 3.13 first.'; exit 1; }
node -e 'if(Number(process.versions.node.split(".")[0])<24)process.exit(1)'
xcode-select -p >/dev/null
python3.13 -m venv .venv
.venv/bin/python -m pip install -r platform/requirements.lock.txt
(cd platform/web && npm ci && npm run build)
echo 'Installed. See README.md for signing WebDriverAgent and starting the API.'
