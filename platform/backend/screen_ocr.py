"""Experimental, local OCR. No device actions, screenshots on disk, or cloud calls."""
import hashlib
import io
import math
from pathlib import Path
import subprocess
import time

from PIL import Image

SOURCE = Path(__file__).resolve().parents[1] / 'native' / 'ocr-screen.swift'


def build(output):
    """Explicit build step; callers choose a private temporary output directory."""
    output = Path(output)
    subprocess.run(['xcrun', 'swiftc', '-O', '-module-cache-path', str(output.parent / 'swift-cache'),
                    str(SOURCE), '-o', str(output)], check=True, capture_output=True, timeout=120)
    return output


def recognize(image, executable, mode='fast'):
    total_started = time.monotonic()
    if mode not in ('fast', 'accurate'):
        raise ValueError('OCR mode must be fast or accurate')
    if not image or len(image) > 16 * 1024 * 1024:
        raise ValueError('Invalid screenshot size')
    with Image.open(io.BytesIO(image)) as frame:
        if frame.width * frame.height > 20_000_000:
            raise ValueError('Screenshot dimensions too large')
        # Bake orientation metadata into pixels before passing to Vision.
        from PIL import ImageOps
        pixels = ImageOps.exif_transpose(frame).convert('RGB')
        dimensions = pixels.size
        buffer = io.BytesIO()
        pixels.save(buffer, format='PNG')
    import json
    started = time.monotonic()
    response = subprocess.run([str(executable), '--' + mode], input=buffer.getvalue(),
                              capture_output=True, timeout=15, check=True)
    result = json.loads(response.stdout)
    if (result['width_px'], result['height_px']) != dimensions:
        raise ValueError('OCR geometry mismatch')
    lines = []
    for item in result['lines']:
        box = item['box']
        if (len(box) != 4 or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in box)
                or not 0 <= box[0] < box[2] <= 1 or not 0 <= box[1] < box[3] <= 1):
            raise ValueError('Invalid OCR bounding box')
        lines.append({**item, 'box': [round(v, 6) for v in box]})
    lines.sort(key=lambda row: (round(row['box'][1] * dimensions[1] / 12), row['box'][0]))
    for i, row in enumerate(lines):
        row['id'] = str(i)
        for j, word in enumerate(row.get('words', [])):
            word['id'] = f'{i}.{j}'
            word['confidence'] = row['confidence']
    return {'image_sha256': hashlib.sha256(image).hexdigest(), 'created': time.monotonic(),
            'mode': mode, 'width_px': dimensions[0], 'height_px': dimensions[1],
            'recognition_ms': round(result['recognition_ms'], 2),
            'process_ms': round((time.monotonic() - started) * 1000, 2),
            'total_ms': round((time.monotonic() - total_started) * 1000, 2),
            'coordinates': 'normalized top-left full-screen xyxy',
            'lines': lines}


def propose_tap(observation, line_id, viewport, current_image, *, now=None, min_confidence=.8):
    """Return a proposal only. Never sends a tap. Exact frame freshness is conservative."""
    age = (time.monotonic() if now is None else now) - observation['created']
    if not 0 <= age <= 15:
        raise ValueError('OCR observation expired; capture again')
    if hashlib.sha256(current_image).hexdigest() != observation['image_sha256']:
        raise ValueError('Screen changed; capture again')
    w, h = viewport['width'], viewport['height']
    if not all(isinstance(v, (int, float)) and math.isfinite(v) and v > 1 for v in (w, h)):
        raise ValueError('Invalid viewport')
    if abs(observation['width_px'] / observation['height_px'] - w / h) > .03:
        raise ValueError('Screenshot and viewport orientations differ')
    candidates = [entry for line in observation['lines'] for entry in [line, *line.get('words', [])]]
    row = next((line for line in candidates if str(line['id']) == str(line_id)), None)
    if not math.isfinite(min_confidence) or not 0 <= min_confidence <= 1:
        raise ValueError('Invalid confidence threshold')
    if not row or not math.isfinite(row['confidence']) or row['confidence'] < min_confidence:
        raise ValueError('Missing or low-confidence OCR target')
    x1, y1, x2, y2 = row['box']
    if not all(math.isfinite(v) for v in row['box']) or not 0 <= x1 < x2 <= 1 or not 0 <= y1 < y2 <= 1:
        raise ValueError('Invalid OCR target geometry')
    x, y = (x1 + x2) / 2, (y1 + y2) / 2
    return {'text': row['text'], 'action': {'action': 'tap', 'x': x, 'y': y},
            'wda_point': {'x': round(x * (w - 1)), 'y': round(y * (h - 1))},
            'requires_review': True,
            'limitation': 'OCR text is not proof that the region is an enabled or tappable control'}
