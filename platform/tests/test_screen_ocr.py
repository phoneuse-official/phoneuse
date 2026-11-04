import hashlib
import io
import os

import pytest
from PIL import Image, ImageDraw, ImageFont

from backend.screen_ocr import propose_tap, recognize


def observation():
    return {'created': 100, 'image_sha256': hashlib.sha256(b'frame').hexdigest(),
            'width_px': 1200, 'height_px': 2400,
            'lines': [{'id': 0, 'text': 'Open product', 'confidence': .99, 'box': [.1, .2, .5, .3]}]}


def test_coordinates_match_existing_wda_point_conversion():
    result = propose_tap(observation(), 0, {'width': 400, 'height': 800}, b'frame', now=105)
    assert result['action'] == {'action': 'tap', 'x': .3, 'y': .25}
    assert result['wda_point'] == {'x': 120, 'y': 200}
    assert result['requires_review'] is True


def test_word_target_avoids_the_center_of_a_mixed_text_line():
    obs = observation()
    obs['lines'][0]['words'] = [{'id': '0.1', 'text': 'product', 'confidence': .5, 'box': [.4, .2, .5, .3]}]
    with pytest.raises(ValueError):
        propose_tap(obs, '0.1', {'width': 400, 'height': 800}, b'frame', now=105)
    result = propose_tap(obs, '0.1', {'width': 400, 'height': 800}, b'frame', now=105, min_confidence=.5)
    assert result['action']['x'] == .45
    assert result['requires_review'] is True


@pytest.mark.parametrize('failure', ['expired', 'changed', 'rotated', 'low_confidence', 'missing', 'nan'])
def test_unsafe_proposals_are_rejected(failure):
    obs = observation(); viewport = {'width': 400, 'height': 800}; image = b'frame'; now = 105; target = 0
    if failure == 'expired': now = 116
    if failure == 'changed': image = b'other frame'
    if failure == 'rotated': viewport = {'width': 800, 'height': 400}
    if failure == 'low_confidence': obs['lines'][0]['confidence'] = .5
    if failure == 'missing': target = 9
    if failure == 'nan': viewport['width'] = float('nan')
    with pytest.raises(ValueError): propose_tap(obs, target, viewport, image, now=now)


@pytest.mark.skipif(not os.environ.get('PHONEUSE_OCR_BINARY'), reason='Explicit local Vision integration test')
@pytest.mark.parametrize('mode', ['fast', pytest.param('accurate', marks=pytest.mark.skipif(
    not os.environ.get('PHONEUSE_OCR_TEST_ACCURATE'), reason='Accurate mode exceeded deadline on the development Mac'))])
def test_real_ocr_text_and_top_left_geometry_on_synthetic_image(mode):
    image = Image.new('RGB', (900, 1800), 'white')
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf', 44)
    draw.text((90, 180), 'Open product', fill='black', font=font)
    draw.text((90, 1350), 'Back to search', fill='black', font=font)
    buffer = io.BytesIO(); image.save(buffer, format='PNG')
    result = recognize(buffer.getvalue(), os.environ['PHONEUSE_OCR_BINARY'], mode)
    top = next(row for row in result['lines'] if row['text'] == 'Open product')
    bottom = next(row for row in result['lines'] if row['text'] == 'Back to search')
    assert .08 < top['box'][0] < .13 and .09 < top['box'][1] < .14
    assert .74 < bottom['box'][1] < .80
    assert result['width_px'] == 900 and result['height_px'] == 1800
