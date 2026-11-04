import io

import pytest
from PIL import Image, ImageDraw
from backend.icon_detection import detect
from backend.icon_detection import attach_accessibility
import json


def fixture(kind, dark=False):
    bg='black' if dark else 'white';fg='white' if dark else 'black'
    im=Image.new('RGB',(400,800),bg);d=ImageDraw.Draw(im)
    if kind=='back':d.line([(38,740),(20,755),(38,770)],fill=fg,width=4)
    elif kind=='close':
        d.line([(350,30),(375,55)],fill=fg,width=4);d.line([(375,30),(350,55)],fill=fg,width=4)
    elif kind=='search':
        d.ellipse((20,30,40,50),outline=fg,width=4);d.line([(38,48),(48,58)],fill=fg,width=4)
    elif kind=='menu':
        for y in (30,40,50):d.line([(20,y),(50,y)],fill=fg,width=4)
    data=io.BytesIO();im.save(data,format='PNG');return data.getvalue()


@pytest.mark.parametrize('kind',['back','close','search','menu'])
@pytest.mark.parametrize('dark',[False,True])
def test_detects_expected_toolbar_shape(kind,dark):
    result=detect(fixture(kind,dark))
    assert any(item['kind']==kind for item in result)
    assert all(0<=v<=1 for item in result for v in item['box'])
    assert all(not item['verified'] for item in result)


def test_blank_screen_has_no_candidates():
    assert detect(fixture('blank'))==[]
    assert detect(fixture('blank',True))==[]


def test_ocr_overlap_excludes_text():
    assert detect(fixture('close'),[{'box':[.85,.02,.97,.09]}])==[]


def test_native_label_is_attached_only_if_unique():
    candidates=[{'box':[.1,.1,.2,.2]}]
    item={'type':'XCUIElementTypeButton','label':'Back','rect':{'x':35,'y':75,'width':60,'height':90}}
    page={'tree':json.dumps(item)}
    assert attach_accessibility(candidates,page,{'width':400,'height':800})[0]['accessibility']['label']=='Back'
    page['tree']+='\n'+json.dumps(item)
    assert 'accessibility' not in attach_accessibility(candidates,page,{'width':400,'height':800})[0]
