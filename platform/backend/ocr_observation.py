"""Task-local OCR screen observations and guarded coordinate taps."""
import base64
import io
import json
import secrets
import tempfile
import time
from pathlib import Path
from PIL import Image
from . import screen_ocr
from .icon_detection import detect
from .visual_targeting import stable_target


class NoOCRContent(ValueError):
    pass


class OCRObservation:
    def __init__(self, phone):
        self.phone=phone;self.current=None;self.temp=None;self.binary=None;self.disabled=False

    def invalidate(self):self.current=None

    def close(self):
        self.invalidate()
        if self.temp:self.temp.cleanup();self.temp=None

    def frame(self):
        raw=base64.b64decode(self.phone.execute({'action':'screenshot'}),validate=True)
        if len(raw)>16*1024*1024:raise ValueError('Screenshot too large')
        with Image.open(io.BytesIO(raw)) as img:
            dims=img.size
            if dims[0]*dims[1]>20_000_000:raise ValueError('Screenshot dimensions too large')
        size=self.phone.execute({'action':'window_size'})
        orientation=self.phone.execute({'action':'orientation'})
        if not all(isinstance(size.get(k),(int,float)) and size[k]>1 for k in ('width','height')):raise ValueError('Invalid viewport')
        if abs(dims[0]/dims[1]-size['width']/size['height'])>.03:raise ValueError('Screenshot aspect ratio mismatch')
        return {'png':raw,'pixels':dims,'size':size,'orientation':orientation}

    def observe(self):
        if self.disabled:raise RuntimeError('Local OCR is unavailable')
        if not self.binary:
            self.temp=tempfile.TemporaryDirectory(prefix='phoneuse-ocr-worker-')
            self.binary=screen_ocr.build(Path(self.temp.name)/'ocr-screen')
        frame=self.frame();result=screen_ocr.recognize(frame['png'],self.binary)
        icons=detect(frame['png'],result['lines'])
        if not result['lines'] and not icons:raise NoOCRContent('OCR found no text or icons')
        revision=secrets.token_hex(16);targets={};rows=[];visible=[]
        with Image.open(io.BytesIO(frame['png'])) as source:
            pixels=source.convert('RGB')
        def blue_hint(box):
            x1,y1,x2,y2=box;w,h=frame['pixels']
            crop=pixels.crop((int(x1*w),int(y1*h),max(int(x1*w)+1,int(x2*w)),max(int(y1*h)+1,int(y2*h))))
            colors=list(crop.get_flattened_data())
            return sum(b>100 and b>r*1.3 and b>g*1.1 for r,g,b in colors)>max(4,len(colors)*.015)
        for row in result['lines'][:120]:
            rows.append(json.dumps({'type':'XCUIElementTypeStaticText','name':row['text']},ensure_ascii=False))
            for word in row.get('words',[]):
                if len(targets)>=240:break
                ref='word-'+str(len(targets));targets[ref]={'text':word['text'],'box':word['box']}
                visible.append({'id':ref,'text':word['text'],'box':[round(v,4) for v in word['box']],
                                'blue_text_hint':blue_hint(word['box'])})
        for icon in icons:
            ref='icon-'+str(len(targets));targets[ref]={'text':icon['kind'],'box':icon['box']}
            visible.append({'id':ref,'text':icon['kind'],'box':icon['box'],'kind':'icon','score':icon['confidence'],'verified':False})
        self.current={**frame,'id':revision,'created':time.monotonic(),'targets':targets,'tree':'\n'.join(rows)}
        return {'tree':'\n'.join(rows),'observation_source':'ocr','observation_id':revision,
                'ocr_targets':visible,'coordinates':'normalized top-left xyxy','ocr_ms':result['total_ms']}

    def tap(self,observation_id,target_id):
        previous=self.current
        if not previous or previous['id']!=observation_id:return {'ok':False,'reason':'stale_ocr_observation'}
        if time.monotonic()-previous['created']>45:
            self.invalidate();return {'ok':False,'reason':'expired_ocr_observation'}
        target=previous['targets'].get(target_id)
        if not target:return {'ok':False,'reason':'unknown_ocr_target'}
        box=target['box'];x1,y1,x2,y2=box
        if not 0<=x1<x2<=1 or not 0<=y1<y2<=1:return {'ok':False,'reason':'invalid_ocr_target'}
        current=self.frame()
        if any(current[k]!=previous[k] for k in ('size','orientation','pixels')) or not stable_target(previous,current,box):
            self.invalidate();return {'ok':False,'reason':'target_region_changed'}
        self.invalidate()
        self.phone.execute({'action':'tap','x':(x1+x2)/2,'y':(y1+y2)/2})
        return {'ok':True}
