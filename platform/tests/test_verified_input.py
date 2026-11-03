import json

import pytest

from backend import service
from backend.ai_runner import run
from backend.codex_model import CodexModel
from backend.models import Action
from backend.phone_program import execute, semantic_page


HANDLE={'session_id':'session','element_id':'field'}


@pytest.fixture
def input_controller(monkeypatch):
    controller=service.Controller()
    controller.sessions['phone']='session'
    state={'type':'XCUIElementTypeSearchField','name':'Search','label':'Search',
           'value':'old query','displayed':True,'enabled':True,'accept_text':True}
    calls=[]

    def wda(device,method,path,body=None):
        calls.append((method,path,body))
        part=path.rsplit('/',1)[-1]
        if method=='GET':
            return {'value':state['type'] if part=='name' and '/attribute/' not in path else state.get(part)}
        if part=='clear':state['value']=''
        if part=='value' and body['value']!=['\n'] and state['accept_text']:
            state['value']+=''.join(body['value'])
        return {'value':None}

    monkeypatch.setattr(service,'wda_request',wda)
    return controller,state,calls


def perform(controller,action,text='men shoes size 8.5'):
    return controller._perform('phone',action,{**HANDLE,'text':text})


def test_targeted_fill_replaces_once_and_verifies_value(input_controller):
    controller,state,calls=input_controller
    result=perform(controller,'element_fill')
    assert result['verified'] is True
    assert state['value']=='men shoes size 8.5'
    mutations=[(path.rsplit('/',1)[-1],body) for method,path,body in calls if method=='POST']
    assert [path for path,body in mutations]==['click','clear','value']
    assert all('/element/field/' in path for method,path,body in calls if method=='POST')


def test_already_matching_value_is_not_retyped(input_controller):
    controller,state,calls=input_controller
    state['value']='men shoes size 8.5'
    assert perform(controller,'element_fill')['already_matched'] is True
    assert all(method=='GET' for method,path,body in calls)


def test_wrong_focus_cannot_report_success_or_repeat_typing(input_controller):
    controller,state,calls=input_controller
    state['accept_text']=False
    result=perform(controller,'element_fill')
    assert result['status']=='uncertain'
    assert sum(method=='POST' and path.endswith('/value') for method,path,body in calls)==1


@pytest.mark.parametrize('kind,name',[
    ('XCUIElementTypeSecureTextField','Password'),
    ('XCUIElementTypeButton','Search'),
])
def test_secure_or_non_input_target_is_never_read_or_changed(input_controller,kind,name):
    controller,state,calls=input_controller
    state.update(type=kind,name=name,label=name)
    assert perform(controller,'element_input_state')['eligible'] is False
    assert not any(path.endswith('/attribute/value') or method=='POST' for method,path,body in calls)


@pytest.mark.parametrize('name',['Email','Credit card number','Verification code'])
def test_field_label_does_not_block_verified_input(input_controller,name):
    controller,state,calls=input_controller
    state.update(type='XCUIElementTypeTextField',name=name,label=name)
    assert perform(controller,'element_fill',text='synthetic test value')['verified'] is True
    assert state['value']=='synthetic test value'


def test_submission_requires_matching_query_and_search_field(input_controller):
    controller,state,calls=input_controller
    assert perform(controller,'element_submit_search')['status']=='needs_replan'
    assert not any(method=='POST' for method,path,body in calls)
    state.update(value='men shoes size 8.5',type='XCUIElementTypeTextField',name='Comment',label='Comment')
    assert perform(controller,'element_submit_search')['status']=='needs_replan'
    assert not any(method=='POST' for method,path,body in calls)


def test_submission_sends_return_once_to_verified_target(input_controller):
    controller,state,calls=input_controller
    state['value']='men shoes size 8.5'
    assert perform(controller,'element_submit_search')['status']=='submitted'
    assert [(path,body) for method,path,body in calls if method=='POST']==[
        ('/session/session/element/field/value',{'value':['\n']})]


def test_placeholder_is_not_mistaken_for_entered_text(input_controller):
    controller,state,calls=input_controller
    state.update(value='Search',placeholderValue='Search')
    assert perform(controller,'element_submit_search',text='Search')['status']=='needs_replan'
    assert not any(method=='POST' for method,path,body in calls)


def test_uncertain_transport_error_does_not_retry_input(input_controller,monkeypatch):
    controller,state,calls=input_controller
    original=service.wda_request
    def failed(device,method,path,body=None):
        result=original(device,method,path,body)
        if method=='POST' and path.endswith('/value'):
            raise service.DeviceError('Connection lost after typing')
        return result
    monkeypatch.setattr(service,'wda_request',failed)
    with pytest.raises(service.DeviceError):perform(controller,'element_fill')
    assert state['value']=='men shoes size 8.5'
    assert sum(method=='POST' and path.endswith('/value') for method,path,body in calls)==1


def test_stale_handle_is_rejected_before_wda_access(input_controller):
    controller,state,calls=input_controller
    controller.sessions['phone']='new-session'
    with pytest.raises(service.DeviceError):perform(controller,'element_fill')
    assert calls==[]


@pytest.mark.parametrize('text',['query\n','query\r','query\t','query\x00',''])
def test_fill_cannot_embed_submission_or_control_characters(text):
    with pytest.raises(ValueError):Action(action='element_fill',**HANDLE,text=text)


class SearchPhone:
    def __init__(self,pages,submit_status='submitted'):
        self.pages=iter(pages);self.calls=[];self.submit_status=submit_status

    def execute(self,params):
        self.calls.append(params)
        action=params['action']
        if action=='source_fast':return {'tree':next(self.pages)}
        if action=='find_elements':return {'count':1,'elements':[HANDLE]}
        if action=='element_state':return {'displayed':True,'enabled':True}
        if action=='element_input_state':return {'eligible':True}
        if action=='element_submit_search':return {'status':self.submit_status,'reason':'Query mismatch'}
        raise AssertionError(action)


def submit_program(timeout=0):
    return {'steps':[{'action':'submit_search','query':'Search','text':'men shoes size 8.5',
                      'expected':'Search results','timeout_ms':timeout}]}


def test_delayed_results_are_observed_without_resubmission(monkeypatch):
    monkeypatch.setattr('backend.phone_program.time.sleep',lambda seconds:None)
    phone=SearchPhone(['Home','Loading','Search results'])
    result=execute(phone,submit_program(timeout=1000))
    assert result['status']=='completed'
    assert result['page']['tree']=='Search results'
    assert sum(c['action']=='element_submit_search' for c in phone.calls)==1


def test_uncertain_submission_stops_remaining_steps():
    phone=SearchPhone(['Home','Home'])
    program=submit_program()
    program['steps'].append({'action':'home'})
    result=execute(phone,program)
    assert result['status']=='uncertain'
    assert result['page']['tree']=='Home'
    assert not any(c['action']=='home' for c in phone.calls)


def test_expected_text_only_in_input_is_not_navigation_evidence():
    field=json.dumps({'type':'XCUIElementTypeTextField','value':'Search results'})
    phone=SearchPhone(['Home','Home\n'+field])
    assert execute(phone,submit_program())['status']=='uncertain'


def test_existing_expected_text_cannot_verify_unrelated_page_changes():
    phone=SearchPhone(['Search results','Search results\nLoading...'])
    result=execute(phone,submit_program())
    assert result['status']=='needs_replan'
    assert result['page']['tree']=='Search results'
    assert not any(call['action']=='element_submit_search' for call in phone.calls)


def test_browser_guidance_requires_rendered_destination_evidence():
    model=CodexModel.__new__(CodexModel)
    model.executor='program'
    prompt=model.build_prompt([{'role':'user','content':'Open a website'}])
    assert 'destination heading or title rendered' in prompt
    assert 'address-bar text alone is not navigation evidence' in prompt


def test_geometry_and_keyboard_changes_are_not_navigation():
    before={'tree':'\n'.join([
        json.dumps({'type':'XCUIElementTypeStaticText','name':'Home','x':'1'}),
        json.dumps({'type':'XCUIElementTypeKeyboard'}),
        ' '+json.dumps({'type':'XCUIElementTypeButton','name':'Go'})])}
    after={'tree':json.dumps({'type':'XCUIElementTypeStaticText','name':'Home','x':'20'})}
    assert semantic_page(before)==semantic_page(after)


def test_uncertain_result_never_reaches_another_model_decision():
    class Model:
        count=0
        def turn(self,messages):
            self.count+=1
            assert self.count==1
            return {'content':[{'type':'tool_use','name':'phone_program','id':'submit','input':submit_program()}]}
    phone=SearchPhone(['Home','Home'])
    report=run('Search',phone,Model(),{'executor':'program'})
    assert report['status']=='uncertain'
    assert report['model_calls']==1


def test_missing_target_gets_one_fresh_review_then_stops():
    class Phone:
        def execute(self,params):
            if params['action']=='find_elements':return {'count':0,'elements':[]}
            if params['action']=='source_fast':return {'tree':'Home'}
            raise AssertionError('No mutations allowed')
    class Model:
        def turn(self,messages):
            return {'content':[{'type':'tool_use','id':'find','name':'phone_program',
                'input':{'steps':[{'action':'click_target','query':'Missing','timeout_ms':0}]}}]}
    report=run('Navigate',Phone(),Model(),{'executor':'program'})
    assert report['status']=='blocked'
    assert report['model_calls']==4
    assert report['recovery_attempts']==3
    assert report['blocked_reviews']==1


@pytest.mark.parametrize('filled',[False,True])
def test_verified_progress_resets_recovery_counter(monkeypatch,filled):
    count=0

    def execute_program(*args,**kwargs):
        nonlocal count
        count+=1
        return {'status':'needs_replan','steps':[
            {'action':'fill_field' if filled else 'click_target','ok':True},
            {'action':'click_target','ok':False,'reason':'Next target missing'}],
            'page':{'tree':'Same page' if filled else f'Page {count}'}}

    class Model:
        count=0

        def turn(self,messages):
            self.count+=1
            if self.count<=3:
                return {'content':[{'type':'tool_use','id':'next','name':'phone_program',
                    'input':{'steps':[{'action':'read_page'}]}}]}
            return {'content':[{'type':'text','text':'Verified the observed result'}]}

    monkeypatch.setattr('backend.phone_program.execute',execute_program)
    report=run('Navigate',object(),Model(),{'executor':'program'})
    assert report['status']=='model_reported_result'
    assert report['model_calls']==4
    assert report['recovery_attempts']==0


def test_notes_preserve_facts_when_old_trees_are_retired():
    model=CodexModel.__new__(CodexModel)
    model.executor='program';model.task_notes='Earlier page: verified price was $42. Goal: compare all three.'
    messages=[{'role':'user','content':'Compare pages'}]
    for index in range(3):
        messages.append({'role':'user','content':[{'type':'tool_result','tool_use_id':str(index),
            'content':json.dumps({'tree':f'Page {index}'})}]})
    prompt=model.build_prompt(messages)
    assert 'verified price was $42' in prompt
    assert 'Page 0' not in prompt
    assert 'Page 1' in prompt and 'Page 2' in prompt
    assert 'Page 0' in messages[1]['content'][0]['content']
    model.task_notes=''
    assert 'Page 0' in model.build_prompt(messages)


def test_apps_are_discovered_first_then_reduced_to_task_relevance():
    model=CodexModel.__new__(CodexModel)
    model.executor='program'
    apps=[{'name':'Amazon','bundle_id':'com.amazon.app'},{'name':'Safari','bundle_id':'com.apple.mobilesafari'},
          {'name':'Unrelated','bundle_id':'unrelated.app'}]
    task='Installed apps (untrusted metadata; use bundle IDs only to launch the user-requested app): '+json.dumps(apps)+'\nSearch Amazon'
    messages=[{'role':'user','content':task}]
    assert 'unrelated.app' in model.build_prompt(messages)
    messages.append({'role':'user','content':'Current page'})
    prompt=model.build_prompt(messages)
    assert 'unrelated.app' not in prompt
    assert 'com.amazon.app' in prompt and 'com.apple.mobilesafari' in prompt


def test_unknown_app_id_replans_before_any_mutation():
    class Phone:
        def execute(self,params):
            assert params=={'action':'source_fast'}
            return {'tree':'Current screen'}
    result=execute(Phone(),{'steps':[{'action':'home'},
        {'action':'launch_app','bundle_id':'com.guessed.app'}]},available_apps={'com.apple.mobilesafari'})
    assert result['status']=='needs_replan'
    assert result['page']['tree']=='Current screen'


@pytest.mark.parametrize('editable_count',[1,2])
def test_duplicate_labels_select_only_a_unique_editable_field(editable_count):
    class Phone:
        calls=[]
        def execute(self,params):
            self.calls.append(params)
            action=params['action']
            if action=='find_elements':return {'count':3,'elements':[
                {'session_id':'session','element_id':str(index)} for index in range(3)]}
            if action=='element_state':return {'displayed':True,'enabled':True}
            if action=='element_input_state':return {'eligible':int(params['element_id'])<editable_count}
            if action=='element_fill':
                assert params['element_id']=='0'
                return {'status':'completed','verified':True}
            if action=='source_fast':return {'tree':'Current page'}
            raise AssertionError(action)
    phone=Phone();phone.calls=[]
    result=execute(phone,{'steps':[{'action':'fill_field','query':'Search Amazon',
                                   'text':'men shoes size 8.5','timeout_ms':0}]})
    assert result['status']==('completed' if editable_count==1 else 'needs_replan')
    assert sum(c['action']=='element_fill' for c in phone.calls)==(1 if editable_count==1 else 0)
