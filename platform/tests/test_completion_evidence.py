import json

from backend.ai_runner import check_completion_evidence, prompt_history, run
from backend.codex_model import compact_schema
from backend.phone_program import TOOL


def result(tree):
    return {'role':'user','content':[{'type':'tool_result','tool_use_id':'read',
        'content':json.dumps({'page':{'tree':tree}})}]}


def goal(quote, status='done'):
    return [{'goal':'Check the price','status':status,'evidence':[quote]}]


def test_evidence_requires_observed_literal_quotes_not_other_tool_data():
    tree=json.dumps({'type':'XCUIElementTypeStaticText','name':'Price: $42'})
    messages=[result(tree),{'role':'assistant','content':'Price: $99'}]
    assert check_completion_evidence(messages,goal('Price: $42'))
    assert not check_completion_evidence(messages,goal('Price: $99'))
    assert not check_completion_evidence(messages,goal('XCUIElementTypeStaticText'))
    assert not check_completion_evidence(messages,goal('Price: $42','uncertain'))
    assert not check_completion_evidence(messages,[])


def test_finish_without_evidence_gets_one_review_then_needs_review():
    class Phone:
        def execute(self,params):return {'tree':'Price: $42'}
    class Model:
        calls=0
        def turn(self,messages):
            self.calls+=1
            if self.calls==1:return {'content':[{'type':'tool_use','id':'read','name':'device_action','input':{'action':'source_fast'}}]}
            return {'content':[{'type':'text','text':'Price is $42'}], 'stop_reason':'finish',
                    'completion_evidence_required':True,'subgoals':goal('Price: $99')}
    model=Model()
    report=run('Find price',Phone(),model,{})
    assert model.calls==3
    assert report['status']=='unverified_result'
    assert report['evidence_status']=='missing_or_unmatched'
    assert report['answer']=='Price is $42'


def test_completion_review_can_correct_quotes_without_new_device_action():
    class Phone:
        calls=0
        def execute(self,params):self.calls+=1;return {'tree':'Price: $42'}
    class Model:
        calls=0
        def turn(self,messages):
            self.calls+=1
            if self.calls==1:return {'content':[{'type':'tool_use','id':'read','name':'device_action','input':{'action':'source_fast'}}]}
            return {'content':[{'type':'text','text':'Price is $42'}], 'stop_reason':'finish',
                    'completion_evidence_required':True,'subgoals':goal('Price: $99' if self.calls==2 else 'Price: $42')}
    phone=Phone()
    report=run('Find price',phone,Model(),{})
    assert report['status']=='model_reported_result'
    assert report['evidence_status']=='quotes_matched'
    assert phone.calls==1


def test_old_pages_keep_bounded_literal_text_but_no_stale_targets():
    old=json.dumps({'type':'XCUIElementTypeStaticText','name':'Harbor $224'})
    messages=[result(old),result('second'),result('third')]
    compact=prompt_history(messages,historical_excerpts=True)
    page=json.loads(compact[0]['content'][0]['content'])['page']
    assert page['historical_text']==['Harbor $224']
    assert 'tree' not in page and 'targets' not in page
    assert json.loads(messages[0]['content'][0]['content'])['page']['tree']==old


def test_compact_schema_keeps_constraints_and_removes_titles():
    original=TOOL['input_schema']
    compact=compact_schema(original)
    assert len(json.dumps(compact)) < len(json.dumps(original))
    assert compact['$defs']['Step']['properties']['action']['enum']==original['$defs']['Step']['properties']['action']['enum']
    assert compact['$defs']['Step']['additionalProperties'] is False
    assert 'title' not in compact['$defs']['Step']
