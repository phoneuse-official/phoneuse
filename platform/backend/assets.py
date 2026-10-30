"""Private, bounded uploads. Filenames are metadata only, never filesystem paths."""
import json
import plistlib
import re
import time
import uuid
import zipfile
from pathlib import Path
from PIL import Image
from .service import STATE, database

ROOT = STATE / 'uploads'
ROOT.mkdir(mode=0o700, exist_ok=True)
MAX_UPLOAD = 128 * 1024 * 1024
MAX_MEDIA = 50 * 1024 * 1024
OWNER_QUOTA = 512 * 1024 * 1024
GLOBAL_QUOTA = 2 * 1024 * 1024 * 1024
RUNNER = 'com.facebook.WebDriverAgentRunner.xctrunner'


def initialize():
    with database() as db:
        db.execute('CREATE TABLE IF NOT EXISTS assets(id TEXT PRIMARY KEY,owner TEXT,name TEXT,kind TEXT,size INTEGER,metadata TEXT,created REAL)')
        known = {r[0] for r in db.execute('SELECT id FROM assets')}
    # Imported once at process startup, before any upload is accepted.
    for path in ROOT.iterdir():
        if re.fullmatch(r'[0-9a-f]{32}', path.name) and path.name not in known:
            path.unlink(missing_ok=True)


def inspect_file(path, name):
    suffix = Path(name).suffix.lower()
    if suffix == '.ipa':
        try:
            with zipfile.ZipFile(path) as archive:
                entries = archive.infolist()
                if len(entries) > 100000 or sum(i.file_size for i in entries) > 2 * 1024**3:
                    raise ValueError('IPA 解压体积过大')
                infos = [i for i in entries if re.fullmatch(r'Payload/[^/]+\.app/Info.plist', i.filename)]
                if len(infos) != 1 or infos[0].file_size > 1024**2:
                    raise ValueError('IPA 需要一个有效应用信息文件')
                info = plistlib.loads(archive.read(infos[0]))
                bundle = info.get('CFBundleIdentifier', '')
                if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{1,249}', bundle):
                    raise ValueError('IPA 应用标识无效')
                return 'ipa', {'bundle_id': bundle, 'name': str(info.get('CFBundleDisplayName', info.get('CFBundleName', bundle)))[:200],
                               'version': str(info.get('CFBundleShortVersionString', ''))[:100]}
        except (zipfile.BadZipFile, plistlib.InvalidFileException, KeyError, TypeError) as exc:
            raise ValueError('IPA 文件结构无效') from exc
    if path.stat().st_size > MAX_MEDIA:
        raise ValueError('图片或视频最大 50 MB')
    if suffix in ('.png', '.jpg', '.jpeg'):
        try:
            with Image.open(path) as im:
                if im.format not in ('PNG', 'JPEG') or im.width * im.height > 40000000:
                    raise ValueError('图片格式或像素尺寸不支持')
                meta = {'width': im.width, 'height': im.height, 'mime': Image.MIME[im.format]}
                im.verify()
                return 'photo', meta
        except (OSError, Image.DecompressionBombError) as exc:
            raise ValueError('图片文件无效') from exc
    if suffix in ('.mp4', '.mov'):
        with path.open('rb') as f:
            header = f.read(32)
        if len(header) < 12 or header[4:8] != b'ftyp':
            raise ValueError('只支持 MP4/MOV 视频容器')
        return 'video', {'mime': 'video/quicktime' if suffix == '.mov' else 'video/mp4'}
    raise ValueError('支持 IPA、PNG、JPEG、MP4 和 MOV 文件')


def get_asset(owner, asset_id):
    with database() as db:
        row = db.execute('SELECT * FROM assets WHERE id=? AND owner=?', (asset_id, owner['hash'])).fetchone()
    if not row:
        raise ValueError('文件不存在或无权访问')
    result = dict(row)
    result['metadata'] = json.loads(result['metadata'])
    return result


def asset_path(asset_id):
    if not re.fullmatch(r'[0-9a-f]{32}', asset_id):
        raise ValueError('文件标识无效')
    return ROOT / asset_id


def register(owner, asset_id, name, size):
    path = asset_path(asset_id)
    kind, meta = inspect_file(path, name)
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        total = db.execute('SELECT COALESCE(SUM(size),0) FROM assets').fetchone()[0]
        own = db.execute('SELECT COALESCE(SUM(size),0) FROM assets WHERE owner=?', (owner['hash'],)).fetchone()[0]
        if own + size > OWNER_QUOTA or total + size > GLOBAL_QUOTA:
            raise ValueError('上传空间已满，请删除不再使用的文件')
        db.execute('INSERT INTO assets VALUES (?,?,?,?,?,?,?)',
                   (asset_id, owner['hash'], name[:200], kind, size, json.dumps(meta), time.time()))
    return get_asset(owner, asset_id)


initialize()
