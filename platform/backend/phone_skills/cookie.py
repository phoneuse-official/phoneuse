"""Conservative direct dismissal of accessibility-visible cookie prompts."""
import json
import re

CHOICES = {'essential cookies only', 'necessary cookies only', 'accept essential cookies',
           'accept necessary cookies', 'reject non-essential cookies', 'reject nonessential cookies',
           'reject all cookies', 'essential only', 'necessary only'}
CONTEXT = re.compile(r'\b(cookie|cookies)\b', re.I)


def records(page):
    rows = []
    for line in page.get('tree', '').splitlines():
        try:
            value = json.loads(line)
            if isinstance(value, dict): rows.append(value)
        except (ValueError, TypeError):
            pass
    return rows


def dismiss_cookie_prompt(context):
    before = context.observe()
    rows = records(before)
    if before.get('truncated') is not False:
        return 'needs_replan', 'A complete accessibility observation is required', before
    if not any(CONTEXT.search(' '.join(str(row.get(k, '')) for k in ('name', 'label', 'value'))) for row in rows):
        return 'needs_replan', 'No cookie prompt was identified', before
    choices = []
    for row in rows:
        if row.get('type') not in ('XCUIElementTypeButton', 'XCUIElementTypeLink') or row.get('text_clipped'):
            continue
        label = row.get('label') or row.get('name') or ''
        if label.strip().casefold() in CHOICES:
            choices.append(label)
    if len(choices) != 1:
        return 'needs_replan', 'No unique essential-only choice was identified', before
    target, reason = context.resolve(choices[0])
    if not target:
        return 'needs_replan', reason, before
    context.click(target)
    after = context.observe()
    remaining = records(after)
    if after.get('truncated') is False and not any(
        CONTEXT.search(' '.join(str(row.get(k, '')) for k in ('name', 'label', 'value')))
        for row in remaining
    ):
        return 'completed', 'Cookie prompt text disappeared after the tap', after
    return 'uncertain', 'Tapped once but dismissal could not be verified', after
