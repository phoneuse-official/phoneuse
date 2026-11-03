"""Device-free targeting regressions, including WDA request counts."""
import base64
import io
import json
import threading
from pathlib import Path

import pytest
from PIL import Image

from backend import service
from backend.ai_runner import compact_source
from backend.codex_api import LocalPhone, TaskRequest
from backend.codex_model import CodexModel
from backend.models import Action
from backend.phone_program import execute, observe, semantic_page
from backend.targeting import References, Target, selectors
from backend.visual_targeting import VisualTargeting

HANDLE={'session_id':'session','element_id':'target'}
ATTRS={'type':'XCUIElementTypeButton','name':'search_id','label':'Search',
       'displayed':True,'enabled':True,'rect':{'x':0,'y':0,'width':100,'height':40}}


def candidate(attrs=None,ident='target'):
    return {**HANDLE,'element_id':ident,'attributes':dict(ATTRS if attrs is None else attrs)}


@pytest.mark.parametrize('label',['Search','بحث','Search "catalog"',"Men's shoes",r'a\b', 'a`b'])
def test_labels_are_data_in_compiled_selectors(label):
    compiled=selectors(Target(label=label,type='XCUIElementTypeButton'))
    assert compiled==[('predicate string',f'label == {json.dumps(label,ensure_ascii=False)} AND type == "XCUIElementTypeButton"')]


def test_class_chain_and_escaped_delimiter_fallback():
    assert selectors(Target(type='XCUIElementTypeButton',label='Search',strategy='class_chain'))[0][0]=='class chain'
    assert selectors(Target(type='XCUIElementTypeButton',label='a`b',strategy='class_chain'))[0][0]=='predicate string'


@pytest.mark.parametrize('payload',[{}, {'type':'Button OR true'}, {'types':['Button']},
    {'ref':'0'*16+':1','label':'Search'}, {'within':{'label':'Toolbar'}}])
def test_invalid_or_mixed_targets_are_rejected(payload):
    with pytest.raises(ValueError):Target.model_validate(payload)


def test_name_miss_falls_back_to_label_predicate(monkeypatch):
    c=service.Controller();c.sessions['phone']='session';calls=[]
    def wda(device,method,path,body=None):
        calls.append(body)
        return {'value':[] if body['using']=='accessibility id' else [{
            'ELEMENT':'target','type':'XCUIElementTypeButton','name':'XCUIElementTypeButton',
            'attribute/name':'internal_search_id','label':'Search','enabled':True,'displayed':True}]}
    monkeypatch.setattr(service,'wda_request',wda)
    result=c._perform('phone','find_elements',{'query':'Search'})
    assert [call['using'] for call in calls]==['accessibility id','predicate string']
    assert result['elements'][0]['attributes']['name']=='internal_search_id'
    assert result['elements'][0]['attributes']['type']=='XCUIElementTypeButton'
    assert all('value' not in item.get('attributes',{}) for item in result['elements'])


@pytest.mark.parametrize('scope_count',[0,1,2])
def test_container_scope_must_be_unique(monkeypatch,scope_count):
    c=service.Controller();c.sessions['phone']='session';paths=[]
    def wda(device,method,path,body=None):
        paths.append(path)
        if len(paths)==1:return {'value':[{'ELEMENT':str(i)} for i in range(scope_count)]}
        assert path=='/session/session/element/0/elements'
        return {'value':[{'ELEMENT':'target'}]}
    monkeypatch.setattr(service,'wda_request',wda)
    result=c._perform('phone','find_elements',{'target':{'label':'Search','within':{'label':'Toolbar'}}})
    assert result['count']==(1 if scope_count==1 else 0)
    assert len(paths)==(2 if scope_count==1 else 1)


@pytest.mark.parametrize('rich,expected_requests',[(False,8),(True,5)])
def test_native_click_reduces_wda_requests_and_keeps_final_checks(monkeypatch,rich,expected_requests):
    c=service.Controller();c.sessions['phone']='session';calls=[]
    def wda(device,method,path,body=None):
        calls.append((method,path))
        if path.endswith('/elements'):
            return {'value':[{'ELEMENT':'target',**(ATTRS if rich else {})}]}
        if path.endswith('/displayed') or path.endswith('/enabled'):return {'value':True}
        if path.endswith('/rect'):return {'value':ATTRS['rect']}
        if '/source?' in path:return {'value':'<App name="Results"/>'}
        if path.endswith('/click'):return {'value':None}
        raise AssertionError(path)
    monkeypatch.setattr(service,'wda_request',wda)
    class Phone:
        def execute(self,params):
            command=Action.model_validate(params)
            value=c._perform('phone',command.action,command.model_dump(exclude_none=True))
            return compact_source(value) if command.action=='source_fast' else value
    result=execute(Phone(),{'steps':[{'action':'click_target','query':'Search'}]})
    assert result['status']=='completed'
    assert len(calls)==expected_requests
    click=next(i for i,(method,path) in enumerate(calls) if path.endswith('/click'))
    assert [path.rsplit('/',1)[-1] for _,path in calls[click-2:click]]==['displayed','enabled']
    assert sum(path.endswith('/click') for _,path in calls)==1


@pytest.mark.parametrize('displayed,enabled',[(False,True),(True,False)])
def test_enriched_state_never_bypasses_final_click_checks(monkeypatch,displayed,enabled):
    c=service.Controller();c.sessions['phone']='session';calls=[]
    def wda(device,method,path,body=None):
        calls.append(method)
        return {'value':displayed if path.endswith('/displayed') else enabled}
    monkeypatch.setattr(service,'wda_request',wda)
    with pytest.raises(service.DeviceError):c._perform('phone','element_click',HANDLE)
    assert 'POST' not in calls


class FocusPhone:
    def __init__(self,editors=1):
        self.calls=[];self.focused=False;self.filled=False;self.submitted=False;self.editors=editors
    def execute(self,params):
        self.calls.append(params);action=params['action']
        if action=='find_elements':
            if params.get('target',{}).get('types'):
                return {'count':1,'elements':[candidate({**ATTRS,'type':'XCUIElementTypeSearchField'})]} if self.focused else {'count':0,'elements':[]}
            if params.get('target',{}).get('type') in ('XCUIElementTypeSearchField','XCUIElementTypeTextField','XCUIElementTypeTextView'):
                return {'count':self.editors,'elements':[candidate({**ATTRS,'type':'XCUIElementTypeSearchField'},str(i)) for i in range(self.editors)]}
            return {'count':1,'elements':[candidate()]}
        if action=='element_click':self.focused=True;return None
        if action=='element_fill':
            assert self.focused;self.filled=True;return {'status':'completed','verified':True}
        if action=='element_submit_search':
            assert self.filled;self.submitted=True;return {'status':'submitted'}
        if action=='source_fast':return {'tree':'Search results' if self.submitted else 'Home'}
        raise AssertionError(action)


def test_search_focuses_revealed_editor_and_finishes_in_one_program():
    phone=FocusPhone()
    result=execute(phone,{'steps':[{'action':'search','query':'Search',
        'text':'synthetic shoes','expected':'Search results','timeout_ms':0}]})
    assert result['status']=='completed'
    assert sum(c['action']=='element_click' for c in phone.calls)==1
    assert sum(c['action']=='element_fill' for c in phone.calls)==1
    assert sum(c['action']=='element_submit_search' for c in phone.calls)==1
    assert not any(c['action']=='element_state' for c in phone.calls)


def test_ambiguous_revealed_editor_is_not_filled():
    phone=FocusPhone(editors=2)
    result=execute(phone,{'steps':[{'action':'search','query':'Search','text':'test','expected':'Results'}]})
    assert result['status']=='needs_replan'
    assert result['steps'][-1]['reason']=='ambiguous'
    assert not phone.filled and not phone.submitted


def test_definitive_miss_does_not_poll(monkeypatch):
    class Phone:
        calls=[]
        def execute(self,params):
            self.calls.append(params)
            if params['action']=='find_elements':return {'count':0,'elements':[]}
            if params['action']=='source_fast':return {'tree':'Home'}
            raise AssertionError(params)
    monkeypatch.setattr('backend.phone_program.time.sleep',lambda _:pytest.fail('Unexpected retry'))
    phone=Phone()
    result=execute(phone,{'steps':[{'action':'click_target','query':'Missing'}]})
    assert result['steps'][0]['reason']=='missing'
    assert len(phone.calls)==2


def test_wait_target_can_wait_for_a_delayed_control(monkeypatch):
    class Phone:
        count=0
        def execute(self,params):
            if params['action']=='find_elements':
                self.count+=1
                return {'count':0,'elements':[]} if self.count==1 else {'count':1,'elements':[candidate()]}
            if params['action']=='source_fast':return {'tree':'Ready'}
            raise AssertionError(params)
    monkeypatch.setattr('backend.phone_program.time.sleep',lambda _:None)
    assert execute(Phone(),{'steps':[{'action':'wait_target','query':'Ready'}]})['status']=='completed'


def test_observation_returns_revision_bound_references_with_one_discovery():
    class Phone:
        rich_targets=True
        target_refs=References()
        calls=[]
        def execute(self,params):
            self.calls.append(params)
            if params['action']=='source_fast':return {'tree':'Home'}
            if params['action']=='find_elements':return {'count':1,'elements':[candidate()]}
            if params['action']=='element_click':self.target_refs.invalidate();return None
            raise AssertionError(params)
    phone=Phone();page=observe(phone)
    ref=page['targets'][0]['ref']
    result=execute(phone,{'steps':[{'action':'click_target','target':{'ref':ref}}]})
    assert result['status']=='completed'
    assert sum(c['action']=='find_elements' for c in phone.calls)==1
    stale=execute(phone,{'steps':[{'action':'click_target','target':{'ref':ref}}]})
    assert stale['steps'][0]['reason']=='stale_reference'
    assert sum(c['action']=='element_click' for c in phone.calls)==1


def png(color='white',size=(200,400)):
    output=io.BytesIO();Image.new('RGB',size,color).save(output,format='PNG')
    return base64.b64encode(output.getvalue()).decode()


class VisualPhone:
    def __init__(self):
        self.pixels=png();self.orientation='PORTRAIT';self.size={'width':100,'height':200};self.calls=[];self.page={'tree':'Home'}
    def execute(self,params):
        self.calls.append(params)
        if params['action']=='screenshot':return self.pixels
        if params['action']=='window_size':return self.size
        if params['action']=='orientation':return self.orientation
        if params['action']=='source_fast':return self.page
        if params['action']=='tap':return None
        raise AssertionError(params)


def test_visual_tap_uses_normalized_box_and_is_consumed_once():
    phone=VisualPhone();vision=VisualTargeting(phone)
    observation=vision.capture()
    assert vision.tap(observation['observation_id'],(.2,.1,.8,.3))['ok']
    assert phone.calls[-1]=={'action':'tap','x':.5,'y':.2}
    assert not vision.tap(observation['observation_id'],(.2,.1,.8,.3))['ok']
    assert vision.image() is None
    assert 'png' not in observation and 'digest' not in observation


@pytest.mark.parametrize('change',['pixels','orientation','size','expired'])
def test_changed_or_expired_visual_observation_never_taps(change,monkeypatch):
    phone=VisualPhone();vision=VisualTargeting(phone);observation=vision.capture()
    if change=='pixels':phone.pixels=png('black')
    if change=='orientation':phone.orientation='LANDSCAPE'
    if change=='size':phone.size={'width':200,'height':400}
    if change=='expired':vision.current['created']-=46
    assert not vision.tap(observation['observation_id'],(.2,.1,.8,.3))['ok']
    assert not any(c['action']=='tap' for c in phone.calls)


def test_cropped_or_rotated_screenshot_is_not_used():
    phone=VisualPhone();phone.pixels=png(size=(400,200))
    with pytest.raises(ValueError,match='aspect'):VisualTargeting(phone).capture()


def test_visual_tap_transport_failure_cannot_replay():
    phone=VisualPhone();vision=VisualTargeting(phone);observation=vision.capture()
    original=phone.execute
    def failed(params):
        if params['action']=='tap':raise RuntimeError('Unknown outcome')
        return original(params)
    phone.execute=failed
    with pytest.raises(RuntimeError):vision.tap(observation['observation_id'],(.2,.1,.8,.3))
    assert not vision.tap(observation['observation_id'],(.2,.1,.8,.3))['ok']


def test_visual_disabled_by_default():
    assert not TaskRequest(device_id='synthetic',task='Test').visual_fallback
    phone=LocalPhone({},'synthetic','task',threading.Event(),lambda **kw:None)
    assert phone.vision is None


def test_screenshot_attachment_is_ephemeral_and_never_in_prompt(monkeypatch):
    monkeypatch.setenv('PHONEUSE_CODEX_BIN','/synthetic/codex')
    paths=[];updates=[]
    class Process:
        returncode=0
        def __init__(self,args,**kwargs):
            image=Path(args[args.index('--image')+1]);paths.append(image)
            assert image.read_bytes()==b'synthetic-image'
            assert image.stat().st_mode&0o777==0o600
        def communicate(self,prompt=None,timeout=None):
            assert 'synthetic-image' not in prompt
            answer={'kind':'finish','parameters':'{}','answer':'Verified','task_notes':''}
            return '\n'.join([json.dumps({'type':'item.completed','item':{'type':'agent_message','text':json.dumps(answer)}}),
                json.dumps({'type':'turn.completed','usage':{}})]),''
        def poll(self):return 0
    monkeypatch.setattr('backend.codex_model.subprocess.Popen',Process)
    model=CodexModel(image_provider=lambda:b'synthetic-image',progress=lambda **kw:updates.append(kw))
    model.turn([{'role':'user','content':'Test'}])
    assert not paths[0].exists()
    assert updates[-1]['model_timings']['prompt_bytes']>0


def test_local_search_halves_model_turns_on_fixed_navigation_scenario():
    from backend.ai_runner import run
    def measure(programs):
        class Model:
            calls=0
            def turn(self,messages):
                self.calls+=1
                if self.calls<=len(programs):
                    return {'content':[{'type':'tool_use','id':str(self.calls),'name':'phone_program',
                        'input':{'steps':[programs[self.calls-1]]}}]}
                return {'content':[{'type':'text','text':'Verified search results'}]}
        phone=FocusPhone()
        report=run('Search for synthetic shoes',phone,Model(),{'executor':'program'})
        assert report['status']=='model_reported_result'
        assert phone.filled and phone.submitted
        return report['model_calls']
    baseline=measure([
        {'action':'click_target','query':'Search'},
        {'action':'fill_field','query':'Search','text':'synthetic shoes'},
        {'action':'submit_search','query':'Search','text':'synthetic shoes','expected':'Search results','timeout_ms':0}])
    improved=measure([{'action':'search','query':'Search','text':'synthetic shoes','expected':'Search results','timeout_ms':0}])
    assert baseline==4 and improved==2


def test_task_restores_only_the_wda_settings_it_changed(monkeypatch):
    from contextlib import nullcontext
    service.initialize()
    c=service.Controller();c.sessions['synthetic']='session'
    monkeypatch.setattr(service,'controller',c)
    for name in ('reserve','acquire','release','unreserve'):
        monkeypatch.setattr(c,name,lambda *args,**kwargs:None)
    monkeypatch.setattr(c,'lock',lambda _:nullcontext())
    settings={'shouldUseCompactResponses':True,'elementResponseAttributes':'type,label','snapshotMaxDepth':37}
    writes=[]
    def wda(device,method,path,body=None):
        if method=='GET':return {'value':dict(settings)}
        writes.append(body['settings']);settings.update(body['settings']);return {'value':None}
    monkeypatch.setattr(service,'wda_request',wda)
    phone=LocalPhone({'hash':'synthetic'},'synthetic','task',threading.Event(),lambda **kw:None)
    monkeypatch.setattr(phone,'check',lambda:None)
    phone.acquire()
    assert phone.rich_targets
    assert settings['snapshotMaxDepth']==37
    phone.close()
    assert settings=={'shouldUseCompactResponses':True,'elementResponseAttributes':'type,label','snapshotMaxDepth':37}
    assert len(writes)==2


def test_transport_metrics_are_aggregate_and_do_not_include_phone_data(monkeypatch):
    from backend import usb
    from backend.timing import collect
    class Response:
        status=200
        def read(self,limit):return b'{"value": []}'
    class Connection:
        def __init__(self,*args):pass
        def request(self,*args,**kwargs):pass
        def getresponse(self):return Response()
        def close(self):pass
    monkeypatch.setattr(usb,'list_usb',lambda:[{'SerialNumber':'synthetic-device','DeviceID':1}])
    monkeypatch.setattr(usb,'UsbHTTPConnection',Connection)
    metrics={}
    with collect(metrics):
        usb.wda_request('synthetic-device','POST','/session/private-session/elements',{'value':'private-label'})
        usb.wda_request('synthetic-device','GET','/session/private-session/element/private-handle/enabled')
    assert metrics['lookup']['calls']==1 and metrics['state']['calls']==1
    serialized=json.dumps(metrics)
    assert 'private' not in serialized and 'synthetic-device' not in serialized


def test_visual_program_requires_opt_in_before_phone_mutation():
    class Phone:
        def execute(self,params):
            assert params['action']=='source_fast'
            return {'tree':'Home'}
    result=execute(Phone(),{'steps':[{'action':'visual_tap','observation_id':'0'*32,
        'box':[.1,.1,.2,.2],'expected':'Results'}]})
    assert result['status']=='needs_replan'
    assert result['steps'][0]['reason']=='visual_disabled'


def test_structured_input_selector_excludes_same_label_buttons():
    from backend.phone_program import Step,resolve
    class Phone:
        def execute(self,params):
            assert params['target']['label']=='Search'
            assert 'XCUIElementTypeTextView' in params['target']['types']
            return {'count':1,'elements':[candidate({**ATTRS,'type':'XCUIElementTypeTextView'})]}
    target,reason=resolve(Phone(),Step(action='fill_field',query='Search',text='synthetic'),input_step=True)
    assert target and reason is None


def test_focus_uses_actual_active_editor_before_global_field_search():
    from backend.phone_program import Step,focus_editor
    class Phone(FocusPhone):
        supports_active_element=True
        def execute(self,params):
            if params['action']=='active_element':
                self.calls.append(params)
                return candidate({**ATTRS,'type':'XCUIElementTypeSearchField'},ident='focused')
            if params.get('target',{}).get('type'):
                pytest.fail('Should use the focused editor, not search all fields')
            return super().execute(params)
    phone=Phone(editors=3)
    target,reason=focus_editor(phone,Step(action='focus_search',query='Search'))
    assert reason is None and target['element_id']=='focused'
    assert phone.focused


@pytest.mark.parametrize('focused_id',['expected','unrelated'])
@pytest.mark.parametrize('editor_available',[False,True])
def test_explicit_editor_is_not_overridden_by_another_focused_field(focused_id,editor_available):
    class Phone:
        supports_active_element=True

        def __init__(self):
            self.focused=False;self.calls=[];self.submitted=False

        def execute(self,params):
            self.calls.append(params)
            action=params['action']
            attrs={**ATTRS,'type':'XCUIElementTypeSearchField'}
            if action=='find_elements':
                if params.get('target',{}).get('identifier')=='expected_editor':
                    return {'count':1,'elements':[candidate(attrs,ident='expected')]} if self.focused and editor_available else {'count':0,'elements':[]}
                return {'count':1,'elements':[candidate()]}
            if action=='element_click':self.focused=True;return None
            if action=='active_element':return candidate(attrs,ident=focused_id)
            if action=='element_fill':
                assert params['element_id']=='expected'
                return {'status':'completed','verified':True}
            if action=='element_submit_search':self.submitted=True;return {'status':'submitted'}
            if action=='source_fast':return {'tree':'Results' if self.submitted else 'Home'}
            raise AssertionError(params)

    phone=Phone()
    result=execute(phone,{'steps':[{'action':'search','query':'Search',
        'editor':{'identifier':'expected_editor'},'text':'synthetic query',
        'expected':'Results','timeout_ms':0}]})
    if focused_id=='expected' and editor_available:
        assert result['status']=='completed'
        assert phone.submitted
    else:
        assert result['status']=='needs_replan'
        assert result['steps'][-1]['reason']==('focused_editor_mismatch' if editor_available else 'missing')
        assert not any(call['action'] in ('element_fill','element_submit_search') for call in phone.calls)


def test_visual_focus_checks_active_editor_without_requiring_page_text_change():
    class Phone(VisualPhone):
        supports_active_element=True
        target_refs=References()
        def execute(self,params):
            if params['action']=='source_fast':return {'tree':'Same page'}
            if params['action']=='active_element':
                return candidate({**ATTRS,'type':'XCUIElementTypeSearchField'})
            return super().execute(params)
    phone=Phone();phone.vision=VisualTargeting(phone)
    observation=phone.vision.capture()
    result=execute(phone,{'steps':[{'action':'visual_tap','observation_id':observation['observation_id'],
        'box':[.2,.1,.8,.3],'verify':'editor'}]})
    assert result['status']=='completed'
    assert result['page']['targets'][0]['ref']
    assert sum(c['action']=='tap' for c in phone.calls)==1


def test_no_active_element_is_a_normal_read_result(monkeypatch):
    c=service.Controller();c.sessions['phone']='session'
    def wda(*args,**kwargs):raise service.DeviceError('WDA: no such element')
    monkeypatch.setattr(service,'wda_request',wda)
    assert c._perform('phone','active_element',{}) is None
    assert c.sessions['phone']=='session'


def test_reference_is_rejected_when_screen_content_changed():
    from backend.phone_program import Step,resolve
    class Phone:
        target_refs=References()
        target_page=semantic_page({'tree':'Before'})
        def execute(self,params):
            assert params['action']=='source_fast'
            return {'tree':'After'}
    phone=Phone();ref=phone.target_refs.add(candidate())
    target,reason=resolve(phone,Step(action='click_target',target={'ref':ref}))
    assert target is None and reason=='stale_reference'


def test_multiline_editor_can_receive_verified_single_line_input(monkeypatch):
    c=service.Controller();c.sessions['phone']='session';state={'value':'old'}
    def wda(device,method,path,body=None):
        part=path.rsplit('/',1)[-1]
        if method=='GET':
            if part in ('displayed','enabled'):return {'value':True}
            if part=='name' and '/attribute/' not in path:return {'value':'XCUIElementTypeTextView'}
            return {'value':state.get(part,'Message')}
        if part=='clear':state['value']=''
        if part=='value':state['value']=''.join(body['value'])
        return {'value':None}
    monkeypatch.setattr(service,'wda_request',wda)
    result=c._perform('phone','element_fill',{**HANDLE,'text':'synthetic test text'})
    assert result['verified'] and state['value']=='synthetic test text'


def test_text_inside_editor_descendants_is_not_destination_evidence():
    page={'tree':'\n'.join([json.dumps({'type':'XCUIElementTypeTextView'}),
        ' '+json.dumps({'type':'XCUIElementTypeStaticText','name':'Search results'}),
        json.dumps({'type':'XCUIElementTypeStaticText','name':'Home'})])}
    assert semantic_page(page)==[{'type':'XCUIElementTypeStaticText','name':'Home'}]


def test_visual_tap_tolerates_animation_outside_target_guard_band():
    phone=VisualPhone();vision=VisualTargeting(phone);observation=vision.capture()
    image=Image.new('RGB',(200,400),'white')
    from PIL import ImageDraw
    ImageDraw.Draw(image).rectangle((140,0,199,90),fill='black')
    output=io.BytesIO();image.save(output,format='PNG')
    phone.pixels=base64.b64encode(output.getvalue()).decode()
    assert vision.tap(observation['observation_id'],(.1,.65,.4,.8))['ok']


def test_visual_tap_rejects_change_inside_target_guard_band():
    phone=VisualPhone();vision=VisualTargeting(phone);observation=vision.capture()
    image=Image.new('RGB',(200,400),'white')
    from PIL import ImageDraw
    ImageDraw.Draw(image).rectangle((20,260,80,320),fill='black')
    output=io.BytesIO();image.save(output,format='PNG')
    phone.pixels=base64.b64encode(output.getvalue()).decode()
    result=vision.tap(observation['observation_id'],(.1,.65,.4,.8))
    assert not result['ok'] and result['reason']=='target_region_changed'
    assert not any(call['action']=='tap' for call in phone.calls)


def test_visual_tap_rejects_layout_movement_even_if_pixels_match():
    phone=VisualPhone()
    def page(y):
        return {'tree':json.dumps({'type':'XCUIElementTypeButton','name':'Synthetic target',
            'x':10,'y':y,'width':30,'height':20})}
    phone.page=page(100)
    vision=VisualTargeting(phone);observation=vision.capture();phone.page=page(120)
    result=vision.tap(observation['observation_id'],(.1,.5,.4,.6))
    assert not result['ok'] and result['reason']=='screen_layout_changed'
