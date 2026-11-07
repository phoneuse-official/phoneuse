"""Opt-in, read-only OCR benchmark. Does not send taps or model requests."""
import argparse
import base64
import json
import os
from pathlib import Path
import statistics
import subprocess
import tempfile
import time
import urllib.request

from backend.screen_ocr import build, recognize


def capture():
    from backend.config import setting
    state = Path(setting('STATE_DIR') or Path(__file__).resolve().parent / '.state')
    key = (state / 'admin-token').read_text().strip()
    def request(path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request('http://127.0.0.1:8765' + path, data=data,
            headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.load(response)
    if any(t['status'] == 'running' for t in request('/api/ai/tasks')['tasks']):
        raise RuntimeError('Wait for the active phone task to finish')
    devices = request('/api/devices')['devices']
    ready = [d for d in devices if d.get('automation') == 'ready']
    if len(ready) != 1:
        raise RuntimeError('Capture requires exactly one ready phone')
    lease = ready[0].get('lease')
    if lease and not lease.get('mine'):
        raise RuntimeError('The phone is leased by another user')
    if not lease:
        # The API requires a lease even for reads. It expires automatically;
        # DELETE would also block the user's existing live-screen viewer.
        request('/api/devices/' + ready[0]['id'] + '/lease', {'seconds': 30})
    path = '/api/devices/' + ready[0]['id'] + '/actions'
    started = time.monotonic()
    image = base64.b64decode(request(path, {'action': 'screenshot'})['value'], validate=True)
    capture_ms = round((time.monotonic() - started) * 1000, 2)
    viewport = request(path, {'action': 'window_size'})['value']
    return image, viewport, capture_ms


def private_json(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--capture', action='store_true', help='Explicitly allow one WDA screenshot; no native capture')
    source.add_argument('--image', type=Path, help='Analyze an existing screenshot offline')
    parser.add_argument('--binary', type=Path, help='Previously built ocr-screen executable')
    parser.add_argument('--runs', type=int, choices=range(1, 11), default=3)
    parser.add_argument('--mode', choices=('fast', 'accurate', 'both'), default='fast')
    parser.add_argument('--save-frame', type=Path, help='Explicitly save the captured frame outside git for visual QA')
    parser.add_argument('--output', type=Path, help='Private report, including recognized screen text; keep outside git')
    args = parser.parse_args()
    image, viewport, capture_ms = capture() if args.capture else (args.image.read_bytes(), None, None)
    if args.save_frame:
        fd = os.open(args.save_frame, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'wb') as stream: stream.write(image)
    with tempfile.TemporaryDirectory(prefix='phoneuse-ocr-') as temp:
        binary = args.binary or build(Path(temp) / 'ocr-screen')
        modes = {}
        for mode in (('fast', 'accurate') if args.mode == 'both' else (args.mode,)):
            # Keep cold start separate; repeated runs use exactly the same frame.
            try:
                cold = recognize(image, binary, mode)
                runs = [recognize(image, binary, mode) for _ in range(args.runs)]
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
                modes[mode] = {'error': type(exc).__name__}
                continue
            modes[mode] = {'cold_process_ms': cold['process_ms'],
                'median_process_ms': statistics.median(r['process_ms'] for r in runs),
                'median_total_ms': statistics.median(r['total_ms'] for r in runs),
                'median_recognition_ms': statistics.median(r['recognition_ms'] for r in runs),
                'line_count': len(runs[-1]['lines']), 'observation': runs[-1]}
        report = {'capture_ms': capture_ms, 'viewport': viewport, 'runs_per_mode': args.runs, 'modes': modes,
                  'scope': 'One unchanged screen; local OCR only; no taps or cloud requests'}
        if args.output:
            private_json(args.output, report)
        print(json.dumps({'capture_ms': capture_ms, 'modes': {
            mode: {k: v for k, v in value.items() if k != 'observation'} for mode, value in modes.items()}}, indent=2))


if __name__ == '__main__':
    main()
