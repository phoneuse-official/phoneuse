import base64
import io
import json
from types import SimpleNamespace
import pytest
from PIL import Image
from backend import phone_program
from backend.ai_runner import check_completion_evidence, prompt_history
from backend.ocr_observation import OCRObservation
from backend.codex_api import TaskRequest
from backend.usb import DeviceError


def png(color='white'):
    data=io.BytesIO();Image.new('RGB',(400,800),color).save(data,format='PNG');return data.getvalue()


class Phone:
    def __init__(self):self.calls=[];self.image=png();self.ocr=OCRObservation(self)
    def execute(self,params):
        self.calls.append(params)
        if params['action']=='screenshot':return base64.b64encode(self.image).decode()
        if params['action']=='window_size':return {'width':400,'height':800}
        if params['action']=='orientation':return 'PORTRAIT'
        if params['action']=='source_fast':return {'tree':json.dumps({'type':'XCUIElementTypeStaticText','name':'Native fallback'})}
        if params['action']=='tap':return None
        raise AssertionError(params)


def test_ocr_observation_provides_evidence_and_guarded_targets(monkeypatch):
    phone=Phone();phone.ocr.binary='/fake'
    monkeypatch.setattr('backend.ocr_observation.screen_ocr.recognize',lambda *args:{
        'lines':[{'text':'Open product','box':[.1,.2,.5,.3],
                  'words':[{'text':'Open','box':[.1,.2,.2,.3]},{'text':'product','box':[.2,.2,.5,.3]}]}], 'total_ms':2})
    monkeypatch.setattr('backend.ocr_observation.detect',lambda *args:[])
    page=phone_program.screen(phone)
    assert page['observation_source']=='ocr' and len(page['ocr_targets'])==2
    assert not any(c['action']=='source_fast' for c in phone.calls)
    messages=[{'role':'user','content':[{'type':'tool_result','content':json.dumps({'page':page})}]}]
    assert check_completion_evidence(messages,[{'goal':'Read page','status':'done','evidence':['Open product']}])
    assert phone.ocr.tap(page['observation_id'],'word-1')['ok']
    assert phone.calls[-1]=={'action':'tap','x':.35,'y':.25}
    assert not phone.ocr.tap(page['observation_id'],'word-1')['ok']


def test_api_defaults_to_local_ocr_and_keeps_screenshot_sharing_opt_in():
    request=TaskRequest(device_id='synthetic',task='Open a page')
    assert request.screen_mode=='ocr' and request.visual_fallback is False
    assert TaskRequest(device_id='synthetic',task='Open a page',screen_mode='accessibility').screen_mode=='accessibility'


def test_changed_screenshot_prevents_ocr_tap(monkeypatch):
    phone=Phone();phone.ocr.binary='/fake'
    monkeypatch.setattr('backend.ocr_observation.screen_ocr.recognize',lambda *args:{
        'lines':[{'text':'Open','box':[.1,.2,.3,.3],'words':[{'text':'Open','box':[.1,.2,.3,.3]}]}], 'total_ms':2})
    monkeypatch.setattr('backend.ocr_observation.detect',lambda *args:[])
    page=phone_program.screen(phone);phone.image=png('black')
    assert phone.ocr.tap(page['observation_id'],'word-0')['reason']=='target_region_changed'
    assert not any(c['action']=='tap' for c in phone.calls)


def test_ocr_failure_falls_back_and_does_not_repeat_build():
    class Broken:
        disabled=False
        def observe(self):raise OSError('OCR unavailable')
        def invalidate(self):pass
    phone=Phone();phone.ocr=Broken()
    page=phone_program.screen(phone)
    assert page['observation_source']=='accessibility_fallback' and phone.ocr.disabled
    assert phone_program.screen(phone)['observation_source']=='accessibility_fallback'


def test_empty_screen_uses_accessibility_for_that_observation_only():
    from backend.ocr_observation import NoOCRContent
    class Empty:
        disabled=False
        def observe(self):raise NoOCRContent('Loading')
        def invalidate(self):pass
    phone=Phone();phone.ocr=Empty()
    assert phone_program.screen(phone)['observation_source']=='accessibility_fallback'
    assert not phone.ocr.disabled


def test_retired_ocr_observations_drop_target_references():
    messages=[]
    for i in range(3):
        page={'tree':json.dumps({'type':'XCUIElementTypeStaticText','name':str(i)}),
              'ocr_targets':[{'id':'word-0'}], 'observation_id':'a'*32}
        messages.append({'role':'user','content':[{'type':'tool_result','content':json.dumps({'page':page})}]})
    old=json.loads(prompt_history(messages,recent_observations=1)[0]['content'][0]['content'])['page']
    assert 'ocr_targets' not in old and 'observation_id' not in old


class SubmissionPhone:
    def __init__(self,kind='XCUIElementTypeSearchField',destination=False,unavailable=False):
        self.calls=[];self.submissions=0
        self.kind=kind;self.destination=destination;self.unavailable=unavailable
        self.ocr=SimpleNamespace(disabled=False,observe=lambda:pytest.fail('Destination verification must not use OCR'))

    def execute(self,params):
        self.calls.append(params)
        action=params['action']
        if action=='find_elements':
            return {'count':1,'elements':[{'session_id':'synthetic','element_id':'search',
                'attributes':{'type':'XCUIElementTypeSearchField','displayed':True,'enabled':True}}]}
        if action=='element_submit_search':self.submissions+=1;return {'status':'submitted'}
        if action=='source_fast':
            rows=[json.dumps({'type':'XCUIElementTypeStaticText','name':'Home'})]
            if self.submissions:
                if self.unavailable:raise DeviceError('Native source unavailable')
                rows.extend([json.dumps({'type':'XCUIElementTypeStaticText','name':'Loading...'}),
                    json.dumps({'type':self.kind,'value':'Search results'}),
                    ' '+json.dumps({'type':'XCUIElementTypeStaticText','name':'Search results'})])
                if self.destination:rows.append(json.dumps({'type':'XCUIElementTypeStaticText','name':'Search results'}))
            return {'tree':'\n'.join(rows)}
        raise AssertionError(params)


def submit_program():
    return {'steps':[{'action':'submit_search','query':'Search','text':'Search results',
        'expected':'Search results','timeout_ms':0}]}


@pytest.mark.parametrize('kind',['XCUIElementTypeTextField','XCUIElementTypeSearchField',
    'XCUIElementTypeTextView','XCUIElementTypeSecureTextField','XCUIElementTypeKeyboard'])
def test_ocr_mode_cannot_verify_destination_from_input_or_keyboard_text(kind):
    phone=SubmissionPhone(kind=kind)
    result=phone_program.execute(phone,submit_program())
    assert result['status']=='uncertain'
    assert phone.submissions==1


def test_ocr_mode_accepts_new_native_destination_content():
    phone=SubmissionPhone(destination=True)
    result=phone_program.execute(phone,submit_program())
    assert result['status']=='completed'
    assert phone.submissions==1
    assert 'Search results' in result['page']['tree']


def test_missing_native_evidence_after_submit_stops_without_resubmission():
    phone=SubmissionPhone(unavailable=True)
    result=phone_program.execute(phone,submit_program())
    assert result['status']=='uncertain'
    assert phone.submissions==1
    assert result['page']['verification_error']=='Native destination evidence unavailable'


@pytest.mark.parametrize('action',['ocr_tap','visual_tap'])
@pytest.mark.parametrize('destination',[False,True])
def test_coordinate_taps_also_require_native_destination_evidence(action,destination):
    phone=SubmissionPhone(destination=destination)

    def tap(*args):
        phone.submissions+=1
        return {'ok':True}

    phone.ocr.current={'id':'a'*32,'tree':'Home'}
    phone.ocr.tap=tap
    phone.vision=SimpleNamespace(tap=tap)
    step={'action':action,'observation_id':'a'*32,'expected':'Search results','timeout_ms':0}
    step.update({'ocr_target':'word-0'} if action=='ocr_tap' else {'box':[.1,.1,.2,.2]})
    result=phone_program.execute(phone,{'steps':[step]})
    assert result['status']==('completed' if destination else 'uncertain')
    assert phone.submissions==1
