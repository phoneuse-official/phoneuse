"""Issue a scoped local API key. Prints the new key exactly once."""
import argparse
import secrets
from datetime import datetime
from backend.service import add_key

parser = argparse.ArgumentParser()
parser.add_argument('--name', required=True)
parser.add_argument('--device', action='append', required=True)
parser.add_argument('--expires-at', help='带时区的ISO到期时间，例如2026-10-01T00:00:00+08:00')
args = parser.parse_args()
expires=None
if args.expires_at:
    date=datetime.fromisoformat(args.expires_at)
    if date.tzinfo is None:parser.error('到期时间必须包含时区')
    expires=date.timestamp()
token = secrets.token_urlsafe(32)
add_key(token, args.name, args.device, expires=expires)
print(token)
