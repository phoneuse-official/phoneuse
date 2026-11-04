"""Synthetic regressions for late-tree controls and selected, complete screen records."""
import json
import xml.etree.ElementTree as ET
import pytest

from backend.ai_runner import compact_source
from backend.phone_program import observe
from backend.targeting import References


def app():
    return ET.Element('XCUIElementTypeApplication',{'type':'XCUIElementTypeApplication',
        'name':'Synthetic Store','x':'0','y':'0','width':'400','height':'850'})


def node(parent,kind,name,**attrs):
    return ET.SubElement(parent,kind,{'type':kind,'name':name,'label':name,'enabled':'true',
        'x':'10','y':'100','width':'250','height':'40',**{key:str(value) for key,value in attrs.items()}})


def source(root):
    return {'source':ET.tostring(root,encoding='unicode'),'excluded_attributes':['visible','accessible']}


def records(page):
    return [json.loads(line) for line in page['tree'].splitlines()]


def test_whole_tree_selection_preserves_controls_beyond_old_cutoff():
    root=app()
    panel=node(root,'XCUIElementTypeOther',('Synthetic assistant panel '+('irrelevant text '*1000)),y=820,height=700)
    for i in range(300):
        node(panel,'XCUIElementTypeOther','Repeated assistant wrapper '+str(i)+' '+('aggregate child content '*100),y=900+i,height=100)
    node(root,'XCUIElementTypeButton',"Men's Shoe Size",y=220)
    node(root,'XCUIElementTypeStaticText','Results',y=700)
    node(root,'XCUIElementTypeButton','Synthetic walking shoe 8.5',y=770)
    xml=source(root)
    assert xml['source'].index("Men's Shoe Size")>32000
    page=compact_source(xml,limit=4000,task='Find walking shoes size 8.5')
    assert len(page['tree'])<=4000
    names=[row.get('name') for row in records(page)]
    assert "Men's Shoe Size" in names and 'Results' in names
    assert 'Synthetic walking shoe 8.5' in names
    assert page['selection']=='whole_tree_viewport_and_task_priority'
    assert page['omitted']['layout']>=1


def test_complete_records_are_never_cut_in_the_middle_of_json():
    root=app()
    for i in range(100):node(root,'XCUIElementTypeButton',f'Synthetic control {i}',y=(i%15)*45)
    page=compact_source(source(root),limit=1200)
    assert page['truncated'] and len(page['tree'])<=1200
    assert records(page) and page['selected_nodes']==len(records(page))


def test_task_relevant_late_control_outranks_unrelated_controls():
    root=app()
    for i in range(100):node(root,'XCUIElementTypeButton',f'Unrelated setting {i}',y=100)
    node(root,'XCUIElementTypeButton','Choose pantry filter',y=100)
    page=compact_source(source(root),limit=1400,task='Choose the pantry filter')
    assert 'Choose pantry filter' in page['tree']


def test_hidden_and_secure_descendants_are_not_model_evidence():
    root=app()
    hidden=node(root,'XCUIElementTypeOther','Hidden overlay',visible='false')
    node(hidden,'XCUIElementTypeButton','Hidden action')
    secret=node(root,'XCUIElementTypeSecureTextField','Password',value='synthetic-secret')
    node(secret,'XCUIElementTypeStaticText','synthetic-secret')
    page=compact_source(source(root))
    assert 'Hidden action' not in page['tree']
    assert 'synthetic-secret' not in page['tree']
    assert page['omitted']['hidden']==2


def test_repeated_layout_labels_and_duplicate_records_are_removed():
    root=app();layout=node(root,'XCUIElementTypeOther','Child label '*100)
    node(layout,'XCUIElementTypeStaticText','Child label')
    node(root,'XCUIElementTypeButton','Unique control')
    node(root,'XCUIElementTypeButton','Unique control')
    page=compact_source(source(root))
    assert page['omitted']['duplicate']==1 and page['omitted']['layout']==1
    assert 'Child label' in page['tree']
    assert 'Child label Child label' not in page['tree']


def test_budget_is_balanced_across_viewport_bands():
    root=app()
    for i in range(50):node(root,'XCUIElementTypeButton',f'Header control {i}',y=30)
    node(root,'XCUIElementTypeButton','Bottom control',y=730)
    assert 'Bottom control' in compact_source(source(root),limit=1000)['tree']


@pytest.mark.parametrize('limit',[True,0,255,1.5])
def test_invalid_screen_budget_is_rejected(limit):
    with pytest.raises(ValueError):compact_source(source(app()),limit=limit)


def test_relevant_native_reference_is_not_lost_after_first_32_matches():
    class Phone:
        rich_targets=True
        target_refs=References()
        task_text='Choose pantry filter'
        def execute(self,params):
            if params['action']=='source_fast':return {'tree':'Home'}
            elements=[]
            for i in range(80):
                elements.append({'session_id':'session','element_id':str(i),'attributes':{
                    'type':'XCUIElementTypeButton','name':'Unrelated '+str(i),'displayed':True,'enabled':True}})
            elements.append({'session_id':'session','element_id':'wanted','attributes':{
                'type':'XCUIElementTypeButton','name':'Choose pantry filter','displayed':True,'enabled':True}})
            return {'count':len(elements),'elements':elements}
    page=observe(Phone())
    assert page['targets'][0]['name']=='Choose pantry filter'
    assert len(page['targets'])==32


def test_blocked_decision_gets_one_fresh_screen_review_and_can_recover():
    from backend.ai_runner import run
    class Phone:
        clicked=False
        def execute(self,params):
            action=params['action']
            if action=='source_fast':return {'tree':'Destination' if self.clicked else 'Visible results'}
            if action=='find_elements':
                return {'count':1,'elements':[{'session_id':'session','element_id':'target',
                    'attributes':{'type':'XCUIElementTypeButton','enabled':True,'displayed':True}}]}
            if action=='element_click':self.clicked=True;return None
            raise AssertionError(action)
    class Model:
        calls=0
        def turn(self,messages):
            self.calls+=1
            if self.calls==1:
                return {'content':[{'type':'tool_use','id':'read','name':'phone_program',
                    'input':{'steps':[{'action':'read_page'}]}}]}
            if self.calls==2:
                return {'stop_reason':'blocked','content':[{'type':'text','text':'A hidden control must be blocking the page'}]}
            if self.calls==3:
                assert 'Recovery review' in messages[-1]['content']
                assert 'Visible results' in messages[-1]['content']
                return {'content':[{'type':'tool_use','id':'next','name':'phone_program',
                    'input':{'steps':[{'action':'click_target','query':'Visible result'}]}}]}
            return {'content':[{'type':'text','text':'Verified destination'}]}
    phone=Phone();report=run('Open the visible result',phone,Model(),{'executor':'program'})
    assert phone.clicked and report['status']=='model_reported_result'
    assert report['blocked_reviews']==1 and report['model_calls']==4


def test_repeated_blocked_decision_on_same_screen_does_not_loop():
    from backend.ai_runner import run
    class Phone:
        reads=0
        def execute(self,params):
            assert params['action']=='source_fast'
            self.reads+=1
            return {'tree':'Same page'}
    class Model:
        calls=0
        def turn(self,messages):
            self.calls+=1
            if self.calls==1:
                return {'content':[{'type':'tool_use','id':'read','name':'phone_program',
                    'input':{'steps':[{'action':'read_page'}]}}]}
            return {'stop_reason':'blocked','content':[{'type':'text','text':'No available route'}]}
    phone=Phone();report=run('Read a destination',phone,Model(),{'executor':'program'})
    assert report['status']=='blocked' and report['model_calls']==3
    assert phone.reads==2 and report['blocked_reviews']==1


def test_recovery_screenshot_is_captured_only_when_enabled():
    from backend.phone_program import recovery_observation
    class Vision:
        calls=0
        def capture(self):
            self.calls+=1
            return {'observation_id':'synthetic'}
    class Phone:
        vision=None
        def execute(self,params):
            assert params['action']=='source_fast'
            return {'tree':'Current page'}
    phone=Phone()
    assert 'visual' not in recovery_observation(phone)
    phone.vision=Vision()
    review=recovery_observation(phone)
    assert review['visual']['observation_id']=='synthetic' and phone.vision.calls==1


def test_old_recovery_tree_is_retired_with_other_observations():
    from backend.ai_runner import prompt_history,RECOVERY_REVIEW_PREFIX
    review={'page':{'tree':'Old recovery screen','targets':[{'ref':'expired'}]},'recovery_review':True}
    messages=[{'role':'user','content':RECOVERY_REVIEW_PREFIX+json.dumps(review)}]
    for index in range(2):
        messages.append({'role':'user','content':[{'type':'tool_result','tool_use_id':str(index),
            'content':json.dumps({'page':{'tree':f'Current screen {index}'}})}]})
    compact=prompt_history(messages)
    assert 'Old recovery screen' not in compact[0]['content']
    assert 'expired' not in compact[0]['content']
    assert 'recovery_review' in compact[0]['content']
    assert 'Old recovery screen' in messages[0]['content']
