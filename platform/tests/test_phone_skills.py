import json
from types import SimpleNamespace
import pytest
from backend.phone_skills.cookie import dismiss_cookie_prompt
from backend.phone_program import Program, execute
from backend.usb import DeviceError


def page(*labels, truncated=False):
    return {'truncated': truncated, 'tree': '\n'.join(json.dumps({'type':'XCUIElementTypeButton', 'name':label}) for label in labels)}


class Context:
    def __init__(self, before, after):
        self.pages = iter([before, after]); self.clicks = 0
    def observe(self): return next(self.pages)
    def resolve(self, label): return ({'label':label}, None)
    def click(self, target): self.clicks += 1


def test_cookie_skill_verifies_disappearance():
    ctx = Context(page('We use cookies', 'Essential cookies only'), page('Home'))
    assert dismiss_cookie_prompt(ctx)[0] == 'completed'
    assert ctx.clicks == 1


def test_cookie_skill_refuses_ambiguous_or_incomplete_screen():
    for before in (page('Cookies', 'Reject all cookies', 'Essential only'), page('Cookies', 'Reject all cookies', truncated=True)):
        ctx = Context(before, page('Home'))
        assert dismiss_cookie_prompt(ctx)[0] == 'needs_replan'
        assert ctx.clicks == 0


def test_cookie_skill_stops_when_dismissal_unverified():
    ctx = Context(page('Cookies', 'Reject all cookies'), page('Cookies', truncated=True))
    assert dismiss_cookie_prompt(ctx)[0] == 'uncertain'
    assert ctx.clicks == 1


def test_skill_name_is_validated():
    assert Program.model_validate({'steps':[{'action':'run_skill','skill':'dismiss_cookie_prompt'}]})


@pytest.mark.parametrize('unavailable',[None,'before','after'])
def test_cookie_program_uses_native_roles_even_when_ocr_is_enabled(unavailable):
    class Phone:
        def __init__(self):
            self.clicks=0
            self.ocr=SimpleNamespace(disabled=False,observe=lambda:pytest.fail('Cookie skill must use native evidence'))

        def execute(self,params):
            action=params['action']
            if action=='source_fast':
                if unavailable==('after' if self.clicks else 'before'):
                    raise DeviceError('Native source unavailable')
                return page('Home') if self.clicks else page('Cookies','Reject all cookies')
            if action=='find_elements':
                return {'count':1,'elements':[{'session_id':'synthetic','element_id':'reject',
                    'attributes':{'type':'XCUIElementTypeButton','displayed':True,'enabled':True}}]}
            if action=='element_click':self.clicks+=1;return None
            raise AssertionError(params)

    phone=Phone()
    result=execute(phone,{'steps':[{'action':'run_skill','skill':'dismiss_cookie_prompt'}]})
    assert result['status']=={None:'completed','before':'needs_replan','after':'uncertain'}[unavailable]
    assert phone.clicks==(0 if unavailable=='before' else 1)
