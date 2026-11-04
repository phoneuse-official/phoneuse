import json

import pytest

from backend.ai_runner import run
from backend.codex_model import CodexModel
from backend.phone_program import execute


def decision(steps):
    return {'content':[{'type':'tool_use','id':'next','name':'phone_program',
                        'input':{'steps':steps}}]}


class FakePhone:
    def __init__(self, count=1, displayed=True, fail_click=False):
        self.calls=[]
        self.count=count
        self.displayed=displayed
        self.fail_click=fail_click

    def execute(self, params):
        self.calls.append(params)
        action=params['action']
        if action=='source_fast':return {'tree':'Current page'}
        if action=='find_elements':
            return {'count':self.count,'elements':[{'session_id':'session','element_id':'target'}]*self.count}
        if action=='element_state':return {'displayed':self.displayed,'enabled':True}
        if action=='element_click' and self.fail_click:raise RuntimeError('Unknown click outcome')
        return None


def test_two_taps_with_observation_take_four_model_calls_instead_of_ten():
    class Model:
        count=0

        def turn(self,messages):
            self.count+=1
            if self.count>1:
                result=json.loads(messages[-1]['content'][0]['content'])
                assert result['page']['tree']=='Current page'
            if self.count==1:return decision([{'action':'read_page'}])
            if self.count<=3:return decision([{'action':'click_target','query':'Observed label','timeout_ms':0}])
            return {'content':[{'type':'text','text':'Verified the resulting page'}]}

    phone=FakePhone()
    report=run('Navigate to the requested page',phone,Model(),{'executor':'program'})
    assert report['status']=='model_reported_result'
    assert report['model_calls']==4
    assert [call['action'] for call in phone.calls]==[
        'source_fast','find_elements','element_state','element_click','source_fast',
        'find_elements','element_state','element_click','source_fast']


@pytest.mark.parametrize('count,displayed',[(0,True),(2,True),(1,False)])
def test_missing_ambiguous_or_hidden_target_stops_before_mutation(count,displayed):
    phone=FakePhone(count=count,displayed=displayed)
    result=execute(phone,{'steps':[
        {'action':'click_target','query':'Observed label','timeout_ms':0},
        {'action':'home'}]})
    assert result['status']=='needs_replan'
    assert result['page']['tree']=='Current page'
    assert all(call['action'] not in ('element_click','home') for call in phone.calls)


def test_failed_tap_is_not_replayed_or_followed_by_more_actions():
    phone=FakePhone(fail_click=True)
    class Model:
        def turn(self,messages):
            return decision([{'action':'click_target','query':'Observed label','timeout_ms':0},
                             {'action':'home'}])
    report=run('Navigate',phone,Model(),{'executor':'program'})
    assert report['status']=='failed'
    assert [call['action'] for call in phone.calls]==['find_elements','element_state','element_click','source_fast']


def test_global_typing_is_rejected_in_program_mode():
    class Model:
        count=0

        def turn(self,messages):
            self.count+=1
            if self.count==1:
                return {'content':[{'type':'tool_use','id':'search','name':'device_action',
                    'input':{'action':'text','text':'men shoes size 8.5\n'}}]}
            raise AssertionError('Unsafe typing must stop the run')
    phone=FakePhone()
    report=run('Search in the already focused search field',phone,Model(),{'executor':'program'})
    assert report['status']=='failed'
    assert report['model_calls']==1
    assert phone.calls==[]


def test_program_prompt_moves_low_level_checks_out_of_model_decisions():
    model=CodexModel.__new__(CodexModel)
    model.executor='program'
    prompt=model.build_prompt([{'role':'user','content':'Open the requested app'}])
    schema=json.loads(prompt.split('Available device_action schema (kind=action):\n')[1].split('\nConversation')[0])
    assert schema['properties']['action']['enum']==['swipe','active_app']
    assert 'click_target automatically' in prompt
    assert 'then find_elements' not in prompt
    assert 'never replay' in prompt
    model.executor='baseline'
    assert 'then find_elements' in model.build_prompt([])


def test_program_validates_all_steps_before_device_calls():
    phone=FakePhone()
    with pytest.raises(ValueError):
        execute(phone,{'steps':[{'action':'home'},{'action':'launch_app'}]})
    assert phone.calls==[]
