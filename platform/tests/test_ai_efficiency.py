import copy
import json
import pytest

from backend.ai_runner import prompt_history, run, usage_tokens


def test_history_retires_only_old_screens_and_keeps_action_evidence():
    messages=[{'role':'user','content':'Open the requested page'}]
    for index in range(5):
        messages.append({'role':'assistant','content':[{'type':'tool_use','id':str(index),
            'name':'phone_program','input':{'steps':[{'action':'read_page'}]}}]})
        value={'status':'needs_replan','steps':[{'action':'click_target','ok':False}],
            'page':{'tree':'screen data '*3000,'nodes':42,'truncated':False}}
        messages.append({'role':'user','content':[{'type':'tool_result',
            'tool_use_id':str(index),'content':json.dumps(value)}]})
    original=copy.deepcopy(messages)
    compact=prompt_history(messages)
    assert messages==original
    assert compact[0]==messages[0]
    for index in range(5):
        assert compact[1+index*2]==messages[1+index*2]
        result=json.loads(compact[2+index*2]['content'][0]['content'])
        assert result['steps']==[{'action':'click_target','ok':False}]
        assert result['status']=='needs_replan'
        assert ('tree' in result['page'])==(index>=3)
    assert len(json.dumps(compact)) < len(json.dumps(messages))*.5


def test_history_supports_direct_observations_and_preserves_other_results():
    results=[{'tree':'old screen'},{'count':1,'elements':[{'element_id':'target'}]},
             {'tree':'recent screen'},{'tree':'current screen'}]
    messages=[{'role':'user','content':[{'type':'tool_result','tool_use_id':str(i),
        'content':json.dumps(value)}]} for i,value in enumerate(results)]
    compact=prompt_history(messages)
    assert 'tree' not in json.loads(compact[0]['content'][0]['content'])
    assert compact[1:]==messages[1:]


def test_provider_token_buckets():
    assert usage_tokens({'input_tokens':100,'cached_input_tokens':80,'output_tokens':10})==110
    assert usage_tokens({'input_tokens':100,'cache_read_input_tokens':80,
                         'cache_creation_input_tokens':20,'output_tokens':10})==210


def test_cached_usage_does_not_stop_an_authorized_next_action():
    class Model:
        def turn(self,messages):
            if len(messages)==1:
                return {'usage':{'input_tokens':100,'cached_input_tokens':80,'output_tokens':10},
                    'content':[{'type':'tool_use','id':'observe','name':'device_action',
                                'input':{'action':'source_fast'}}]}
            return {'usage':{'input_tokens':10,'output_tokens':5},
                    'content':[{'type':'text','text':'Observed the requested page'}]}
    class Phone:
        def execute(self,params):
            assert params=={'action':'source_fast'}
            return {'tree':'Requested page'}
    report=run('Read the page',Phone(),Model(),{'max_total_reported_tokens':150})
    assert report['status']=='model_reported_result'
    assert report['budget_tokens']==125
    assert report['reported_usage']['cached_input_tokens']==80


def test_budget_still_stops_before_executing_a_device_action():
    class Model:
        def turn(self,messages):
            return {'usage':{'input_tokens':151},'content':[{'type':'tool_use',
                'id':'action','name':'device_action','input':{'action':'home'}}]}
    class Phone:
        def execute(self,params):
            raise AssertionError('Over-budget actions must never execute')
    report=run('Open an app',Phone(),Model(),{'max_total_reported_tokens':150})
    assert report['status']=='token_limit'
    assert report['actions']==[]


def test_default_history_preserves_facts_across_three_screens():
    class Model:
        def turn(self,messages):
            results=[json.loads(block['content']) for message in messages
                     if isinstance(message['content'],list) for block in message['content']
                     if block['type']=='tool_result']
            if len(results)<3:
                return {'content':[{'type':'tool_use','id':str(len(results)),
                    'name':'device_action','input':{'action':'source_fast'}}]}
            assert [result['tree'] for result in results]==['Page 1','Page 2','Page 3']
            return {'content':[{'type':'text','text':'Read all three pages'}]}

    class Phone:
        count=0

        def execute(self,params):
            self.count+=1
            return {'tree':f'Page {self.count}'}

    report=run('Summarize all three pages',Phone(),Model(),{})
    assert report['status']=='model_reported_result'
    assert report['model_calls']==4


@pytest.mark.parametrize('limit',[0,-1,True,1.5,'2'])
def test_history_rejects_invalid_retention_limits(limit):
    with pytest.raises(ValueError,match='positive integer'):
        prompt_history([],limit)


def test_long_task_continues_past_old_step_and_time_limits(monkeypatch):
    from backend import ai_runner
    from backend.codex_api import TaskRequest

    clock=[0.0]
    monkeypatch.setattr(ai_runner.time,'monotonic',lambda:clock[0])

    class Model:
        calls=0

        def turn(self,messages):
            self.calls+=1
            clock[0]+=10
            if self.calls<=35:
                return {'content':[{'type':'tool_use','id':str(self.calls),
                    'name':'device_action','input':{'action':'source_fast'}}]}
            return {'content':[{'type':'text','text':'Verified every subgoal'}]}

    class Phone:
        def execute(self,params):
            return {'tree':'Verified page'}

    request=TaskRequest(device_id='test-phone',task='Complete all subgoals')
    report=run(request.task,Phone(),Model(),{'max_steps':request.max_steps})
    assert report['status']=='model_reported_result'
    assert report['model_calls']==36
    assert report['elapsed_seconds']==360


def test_extended_task_still_stops_at_deadline(monkeypatch):
    from backend import ai_runner

    clock=[0.0]
    monkeypatch.setattr(ai_runner.time,'monotonic',lambda:clock[0])

    class Model:
        def turn(self,messages):
            clock[0]+=301
            return {'content':[{'type':'tool_use','id':str(clock[0]),
                'name':'device_action','input':{'action':'source_fast'}}]}

    class Phone:
        def execute(self,params):
            return {'tree':'Still working'}

    report=run('Read pages',Phone(),Model(),{})
    assert report['status']=='time_limit'
    assert report['model_calls']==2
