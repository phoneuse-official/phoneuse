"""Check staged/tracked source paths and contents, without printing matched secrets."""
from pathlib import Path
import re
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
paths = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
blocked_dirs = {'.state', '.venv', 'node_modules', '__pycache__', 'developer-support', 'phone-software', '.openai', '.vinext', 'dist', '.next', '.wrangler'}
blocked_suffixes = {'.ipa', '.dmg', '.ipsw', '.p12', '.mobileprovision', '.sqlite3', '.db', '.pem', '.key', '.log', '.mp4', '.jpg', '.jpeg'}
patterns = [
    ('private key', re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')),
    ('API credential', re.compile(r'\b(?:sk-proj-|ghp_|github_pat_)[A-Za-z0-9_\-]{20,}')),
    ('local home path', re.compile(r'/Users/[A-Za-z0-9_.-]+/')),
    ('device identifier', re.compile(r'\b[0-9A-Fa-f]{8}-[0-9A-Fa-f]{16}\b')),
]
failures = []
for name in filter(None, paths):
    p = root / name
    if p.is_symlink():
        failures.append((name, 'symlink')); continue
    if blocked_dirs.intersection(p.relative_to(root).parts) or p.suffix.lower() in blocked_suffixes or (p.name.startswith('.env') and p.name != '.env.example'):
        failures.append((name, 'private or generated path')); continue
    if p.stat().st_size > 2_000_000:
        failures.append((name, 'unexpected large file'))
    content = p.read_bytes()
    if b'\x00' in content:
        failures.append((name, 'unexpected binary')); continue
    text = content.decode('utf-8', errors='replace')
    for label, pattern in patterns:
        if pattern.search(text): failures.append((name, label))
for name, reason in failures:
    print(f'{name}: {reason}')
print(f'Checked {len(list(filter(None, paths)))} tracked files; {len(failures)} findings.')
print('Pattern checks do not replace manual review or a dedicated secret scanner.')
sys.exit(bool(failures))
