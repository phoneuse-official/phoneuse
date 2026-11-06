import importlib.util
import json
from pathlib import Path

import pytest
from PIL import Image

spec=importlib.util.spec_from_file_location('ocr_navigation',Path(__file__).resolve().parents[1]/'experiment-ocr-navigation.py')
nav=importlib.util.module_from_spec(spec);spec.loader.exec_module(nav)


def test_target_coordinates_are_bounded():
    assert nav.center({'box':[.2,.4,.4,.6]})==pytest.approx((.3,.5))
    with pytest.raises(ValueError):nav.center({'box':[0,.1,1.1,.5]})


@pytest.mark.parametrize('failure',['outer_response','answer_text'])
def test_invalid_model_json_gets_one_retry_without_phone_actions(failure):
    class Model:
        calls=0
        def turn(self,messages):
            self.calls+=1
            if self.calls==1:
                if failure=='outer_response':raise json.JSONDecodeError('bad','',0)
                return {'content':[{'type':'text','text':'not JSON'}]}
            assert 'invalid JSON' in messages[-1]['content']
            return {'content':[{'type':'text','text':'{"action":"finish","reason":"done"}'}]}
    import io
    frame=io.BytesIO();Image.new('RGB',(4,4),'white').save(frame,format='PNG')
    model=Model();result,_=nav.decision(model,'task',{'lines':[]},frame.getvalue(),'',[])
    assert result['action']=='finish' and model.calls==2


def test_malformed_answer_stops_after_one_retry():
    class Model:
        calls=0
        def turn(self,messages):
            self.calls+=1
            return {'content':[{'type':'text','text':'not JSON'}]}
    import io
    frame=io.BytesIO();Image.new('RGB',(4,4),'white').save(frame,format='PNG')
    model=Model()
    with pytest.raises(json.JSONDecodeError):
        nav.decision(model,'task',{'lines':[]},frame.getvalue(),'',[])
    assert model.calls==2


def test_unexpected_tool_request_is_rejected_without_retry():
    class Model:
        calls=0
        def turn(self,messages):
            self.calls+=1
            return {'content':[{'type':'tool_use','name':'unexpected'}]}
    import io
    frame=io.BytesIO();Image.new('RGB',(4,4),'white').save(frame,format='PNG')
    model=Model()
    with pytest.raises(ValueError,match='Unexpected model tool request'):
        nav.decision(model,'task',{'lines':[]},frame.getvalue(),'',[])
    assert model.calls==1


def test_icon_result_requires_new_expected_text():
    assert nav.icon_result_verified('Home', 'Home Settings', 'Settings')
    assert not nav.icon_result_verified('Home Settings', 'Home Settings changed', 'Settings')
    assert not nav.icon_result_verified('Home', 'Menu', 'Settings')


def test_vision_icon_requires_opt_in_and_valid_box():
    candidate={'word_id':'vision-icon','icon_kind':'back','icon_confidence':.9,'icon_box':[.02,.85,.08,.9]}
    assert nav.vision_icon(candidate,False) is None
    assert nav.vision_icon(candidate,True)['kind']=='back'
    for change in ({'icon_box':[0,0,1,1]}, {'icon_kind':'purchase'}, {'icon_confidence':.2}):
        with pytest.raises(ValueError):nav.vision_icon({**candidate,**change},True)
