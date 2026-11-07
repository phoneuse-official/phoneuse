"""Start the local web app and open it with the local API key, without exposing the key in logs."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.parse

ROOT = Path(__file__).resolve().parent

def reachable(url):
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def main():
    os.chdir(ROOT)
    state = ROOT / '.state'
    state.mkdir(exist_ok=True, mode=0o700)
    api_url = 'http://127.0.0.1:8765/openapi.json'
    if not reachable(api_url):
        for name in ('com.phoneuse.local-node', 'local.qunkong.iphone-node'):
            if subprocess.run(['launchctl', 'kickstart', f'gui/{os.getuid()}/{name}'], check=False, capture_output=True).returncode == 0:
                break
        for _ in range(15):
            if reachable(api_url): break
            time.sleep(1)
        else:
            log = state/'recording-api.log'
            with log.open('ab') as output:
                log.chmod(0o600)
                subprocess.Popen([sys.executable, '-m', 'uvicorn', 'backend.api:app', '--host', '127.0.0.1', '--port', '8765', '--ws-max-size', '4096', '--ws-per-message-deflate', 'false', '--no-access-log'],
                                 cwd=ROOT, stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                                 start_new_session=True)
            for _ in range(30):
                if reachable(api_url): break
                time.sleep(1)
            else:
                raise SystemExit('The local API did not start. Check platform/.state/recording-api.log.')
    if not reachable('http://localhost:3109/'):
        candidates = sorted((Path.home()/'.nvm/versions/node').glob('*/bin/node'), key=lambda p:p.stat().st_mtime, reverse=True)
        node = shutil.which('node') or (str(candidates[0]) if candidates else None)
        if not node: raise SystemExit('Node.js is missing. Install Node 24 before starting.')
        log = state/'recording-web.log'
        with log.open('ab') as output:
            log.chmod(0o600)
            subprocess.Popen([node, str(ROOT/'web/node_modules/vinext/dist/cli.js'), 'dev', '--host', '127.0.0.1', '--port', '3109'],
                             cwd=ROOT/'web', stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                             start_new_session=True)
        for _ in range(40):
            if reachable('http://localhost:3109/'): break
            time.sleep(1)
        else: raise SystemExit('The web app did not start. Check platform/.state/recording-web.log.')
    url = 'http://localhost:3109/'
    token_file = state / 'admin-token'
    if token_file.is_file():
        token = token_file.read_text().strip()
        if token:
            # Fragments stay in the browser; the page clears it immediately.
            url += '#key=' + urllib.parse.quote(token, safe='')
    subprocess.run(['open', url], check=True)
    print('PhoneUse is ready. Connect and unlock your iPhone. No phone content was changed.')

if __name__ == '__main__':
    main()
