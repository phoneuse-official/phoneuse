"""Native Messages draft preparation and an explicit, single-attempt send."""
import base64
import hashlib
import io
import json
import re
import time
from pathlib import Path
from PIL import Image, ImageChops, ImageStat
from . import service

APP = 'com.apple.MobileSMS'
ASSET = Path(__file__).resolve().parents[1] / 'assets/phonebase-invitation.png'
MESSAGE = 'Hey Alex! Design night at the Ferry Building in San Francisco on September 19, 7–8 PM. Would love to see you there!'
EMPTY_COMPOSER_VALUES = frozenset(('', 'iMessage', 'Text Message', 'Text Message • SMS',
                                   'Text Message • MMS', 'Text Message • RCS'))


def empty_composer(value):
    return value in EMPTY_COMPOSER_VALUES


def select_recipient(p, address):
    try:
        expected_digits = re.sub(r'\D', '', address)
        p.act('text', text=address)
        end = time.monotonic() + 6
        while time.monotonic() < end:
            root = p.tree()
            screen_width = float(root.get('width', '0'))
            screen_height = float(root.get('height', '0'))
            parents = {child: parent for parent in root.iter() for child in parent}
            addresses = [n for n in root.iter()
                         if any(re.sub(r'\D', '', n.get(key, '')) == expected_digits
                                for key in ('name', 'label', 'value'))]
            cells = []
            for address_node in addresses:
                node = address_node
                while node is not None and not node.get('type', '').endswith('Cell'):
                    node = parents.get(node)
                if node is not None and node not in cells:
                    cells.append(node)
            if len(cells) > 1:
                raise RuntimeError('Recipient suggestions are ambiguous.')
            if len(cells) == 1 and screen_width > 0 and screen_height > 0:
                cell = cells[0]
                x = (float(cell.get('x')) + float(cell.get('width')) / 2) / screen_width
                y = (float(cell.get('y')) + float(cell.get('height')) / 2) / screen_height
                if cell.get('enabled') == 'true' and 0 < x < 1 and 0 < y < 1:
                    p.act('tap', x=x, y=y)
                    p.cancel.wait(.35)
                    return
            p.cancel.wait(.2)
    except Exception:
        raise RuntimeError('The configured recipient could not be selected. Nothing was sent.') from None
    raise RuntimeError('The configured recipient could not be selected. Nothing was sent.')


def recipient():
    data = json.loads((service.STATE / 'demo-recipient.json').read_text())
    contact_name = data.get('contact_name', '')
    address = data.get('phone', '')
    valid_name = isinstance(contact_name, str) and contact_name == contact_name.strip() and re.fullmatch(r'[^\r\n\t]{1,100}', contact_name)
    if data.get('name') != 'Alex' or not valid_name or not re.fullmatch(r'\+[1-9][0-9]{7,14}', address):
        raise RuntimeError('Configure Alex’s verified Messages contact before this take.')
    return contact_name, address


def inspect(p, address, *, contact_name, require_image=True):
    if p.act('active_app').get('bundleId') != APP:
        raise RuntimeError('Open the prepared Messages draft before sending.')
    root = p.tree()
    fields = [n for n in root.iter() if n.get('name') == 'messageBodyField']
    to = [n for n in root.iter() if n.get('name') == 'To:' and n.get('type', '').endswith('TextField')]
    chips = [n for field in to for n in field.iter() if n.get('type', '').endswith('Button')]
    prefix = contact_name + ', '
    label = chips[0].get('label', '') if len(chips) == 1 else ''
    shown_address = label[len(prefix):] if label.startswith(prefix) else ''
    phone_format = re.fullmatch(r'[+0-9() .\-\u00a0\u202f\u2010\u2011]+', shown_address)
    same_address = phone_format is not None and re.sub(r'\D', '', shown_address) == re.sub(r'\D', '', address)
    if len(fields) != 1 or len(chips) != 1 or not shown_address or not same_address:
        raise RuntimeError('The draft must have exactly one recipient: the configured Alex contact.')
    field = fields[0]
    value = field.get('value', '')
    if require_image and (value.count('\ufffc') != 1 or value.replace('\ufffc', '').strip() != MESSAGE):
        raise RuntimeError('The invitation image or message changed. Review the phone before another take.')
    transport = [field.get('placeholderValue', ''), field.get('label', '')]
    transport += [n.get('label', '') for n in root.iter() if n.get('type', '').endswith('StaticText')]
    imessage = any(t == 'iMessage' or t == 'Message, iMessage' for t in transport)
    if any('SMS' in t or 'MMS' in t or 'RCS' in t for t in transport): imessage = False
    return root, field, imessage


def draft_sample(p, root, field, png):
    # Compare the visible image region at approval and immediately before Send.
    # A changed/scrolling draft fails closed; no send mutation is retried.
    image = Image.open(io.BytesIO(png)).convert('RGB')
    sx = image.width / float(root.get('width')); sy = image.height / float(root.get('height'))
    x = float(field.get('x')); y = max(190, float(field.get('y')))
    w = float(field.get('width'))
    return image.crop((int((x+8)*sx), int(y*sy), int((x+w-8)*sx), int((y+140)*sy))).resize((48, 28)).tobytes()


def verify_artwork(sample, width):
    target = Image.frombytes('RGB', (48, 28), sample)
    source = Image.open(ASSET).convert('RGB')
    width = round(width)
    rendered = source.resize((width-12, round((width-12)*source.height/source.width)))
    for y in range(0, rendered.height-140, 2):
        candidate = rendered.crop((3, y, width-13, y+140)).resize((48, 28))
        if max(ImageStat.Stat(ImageChops.difference(target, candidate)).mean) < 8:
            return
    raise RuntimeError('The visible image does not match the prepared invitation. Nothing was sent.')


def prepare(p):
    contact_name, address = recipient()
    p.act('launch_app', bundle_id=APP); p.cancel.wait(.5)
    if not p.has('messageBodyField'):
        p.click('composeButton', 'Button')
        p.click('To:', 'TextField')
        select_recipient(p, address)
        p.click('messageBodyField')
    _, field, _ = inspect(p, address, contact_name=contact_name, require_image=False)
    value = field.get('value', '')
    if empty_composer(value):
        p.click('messageBodyField')
        root, field = p.find('messageBodyField')
        p.act('long_press', x=(float(field.get('x'))+40)/float(root.get('width')),
              y=(float(field.get('y'))+float(field.get('height'))/2)/float(root.get('height')), duration_ms=900)
        p.click('Paste', 'StaticText')
        _, field, _ = inspect(p, address, contact_name=contact_name, require_image=False)
        if field.get('value', '').replace('\ufffc', '').strip() or field.get('value', '').count('\ufffc') != 1:
            raise RuntimeError('The prepared image is not on the clipboard. Nothing was sent.')
        p.act('text', text=MESSAGE)
    root, field, imessage = inspect(p, address, contact_name=contact_name)
    png = base64.b64decode(p.act('screenshot'), validate=True)
    sample = draft_sample(p, root, field, png)
    verify_artwork(sample, float(field.get('width')))
    return {'recipient': 'Alex', 'recipient_hint': '•••• ' + address[-4:], 'message': MESSAGE,
            'transport': 'iMessage' if imessage else 'SMS / MMS', 'asset_sha256': hashlib.sha256(ASSET.read_bytes()).hexdigest()}, contact_name, address, png, sample


def send(p, contact_name, address, sample, before_send):
    root, field, imessage = inspect(p, address, contact_name=contact_name)
    prior_outgoing = sum(
        MESSAGE in n.get('label', '')
        and ('You' in n.get('label', '') or 'Outgoing' in n.get('label', ''))
        for n in root.iter()
    )
    current = draft_sample(p, root, field, base64.b64decode(p.act('screenshot'), validate=True))
    a = Image.frombytes('RGB', (48, 28), sample); b = Image.frombytes('RGB', (48, 28), current)
    if max(ImageStat.Stat(ImageChops.difference(a, b)).mean) > 8:
        raise RuntimeError('The visible invitation changed after preview. Nothing was sent; prepare a new preview.')
    before_send()  # Persist attempt state before the only irreversible mutation.
    p.click('sendButton', 'Button')
    end = time.monotonic() + 25
    stable = 0
    while time.monotonic() < end:
        p.check()
        root = p.tree()
        labels = [n.get('label', '') for n in root.iter()]
        if any('Not Delivered' in x for x in labels):
            raise RuntimeError('Messages reports Not Delivered. Check the phone; this task will not resend.')
        if any('MMS Messaging needs to be enabled' in x or 'Cannot Send Message' in x or 'Message Send Failure' in x for x in labels):
            raise RuntimeError('Messages could not send the poster. Check MMS availability on the phone; this task will not resend.')
        outgoing = sum(MESSAGE in x and ('You' in x or 'Outgoing' in x) for x in labels)
        fresh_outgoing = outgoing > prior_outgoing
        receipt = any(x == 'Delivered' or x.startswith('Read ') for x in labels)
        fields = [n for n in root.iter() if n.get('name') == 'messageBodyField']
        empty = len(fields) == 1 and empty_composer(fields[0].get('value', ''))
        pending = any('Sending' in x for x in labels) or any(n.get('type', '').endswith('ProgressIndicator') for n in root.iter())
        # SMS/MMS need not expose a delivery receipt. Report only a sent state,
        # after the outgoing bubble is visible and the composer has cleared.
        stable = stable + 1 if fresh_outgoing and empty and not pending else 0
        if fresh_outgoing and empty and not pending and (receipt or stable >= 6):
            return
        p.cancel.wait(.5)
    raise RuntimeError('Send was attempted; its outcome is not yet verified. Check the phone. Do not repeat this take.')
