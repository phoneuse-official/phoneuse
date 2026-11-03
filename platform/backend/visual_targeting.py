"""Opt-in screenshot grounding. Pixels live in memory, never in task metrics/history."""
import base64
import io
import json
import math
import secrets
import time
from PIL import Image, ImageChops, ImageStat
from .screen_observation import rect, intersects, INPUTS

def layout_signature(page):
    """Stable native labels/bounds catch scrolling, overlays, and moved controls.

    Pixel animation in an unrelated video is deliberately not a layout change.
    """
    anchors=[]
    for line in page.get('tree','').splitlines():
        try:attrs=json.loads(line)
        except (ValueError,TypeError):continue
        if not isinstance(attrs,dict):continue
        bounds=rect(attrs)
        if not bounds or intersects(bounds,page.get('viewport')) is False:continue
        name=attrs.get('name') or attrs.get('label') or ''
        if not name and attrs.get('type') not in INPUTS:continue
        anchors.append((attrs.get('type',''),name,str(attrs.get('enabled','true')),
            tuple(round(bounds[key],1) for key in ('x','y','width','height'))))
    return sorted(anchors)


def stable_target(previous,current,box):
    """Compare the intended control and its guard band, not unrelated screen pixels."""
    width,height=previous['pixels'];x1,y1,x2,y2=box
    margin_x=max(.015,12/previous['size']['width'])
    margin_y=max(.015,12/previous['size']['height'])
    crop=(math.floor(max(0,x1-margin_x)*width),math.floor(max(0,y1-margin_y)*height),
          math.ceil(min(1,x2+margin_x)*width),math.ceil(min(1,y2+margin_y)*height))
    with Image.open(io.BytesIO(previous['png'])) as old,Image.open(io.BytesIO(current['png'])) as new:
        difference=ImageChops.difference(old.convert('RGB').crop(crop),new.convert('RGB').crop(crop))
        histogram=difference.convert('L').histogram()
        changed=sum(histogram[25:])/max(1,sum(histogram))
        mean=sum(ImageStat.Stat(difference).mean)/3
        return changed<=.01 and mean<=3


class VisualTargeting:
    def __init__(self, phone):
        self.phone=phone
        self.current=None

    def invalidate(self):
        self.current=None

    def frame(self):
        value=self.phone.execute({'action':'screenshot'})
        raw=base64.b64decode(value,validate=True)
        if len(raw)>16*1024*1024:raise ValueError('Screenshot too large')
        with Image.open(io.BytesIO(raw)) as img:
            if img.width*img.height>20_000_000:raise ValueError('Screenshot dimensions too large')
            # Re-encode as PNG so the CLI input has a known format regardless of WDA quality.
            pixels=img.convert('RGB')
            output=io.BytesIO();pixels.save(output,format='PNG')
            dimensions=pixels.size
        size=self.phone.execute({'action':'window_size'})
        orientation=self.phone.execute({'action':'orientation'})
        if not all(isinstance(size.get(k),(int,float)) and size[k]>0 for k in ('width','height')):
            raise ValueError('Invalid screen geometry')
        # Screenshots must represent the complete, unrotated viewport, not a crop.
        if abs(dimensions[0]/dimensions[1]-size['width']/size['height'])>.03:
            raise ValueError('Screenshot and viewport aspect ratios differ')
        page=self.phone.execute({'action':'source_fast'})
        return {'png':output.getvalue(),'size':size,'layout':layout_signature(page),
                'orientation':orientation,'pixels':dimensions}

    def capture(self):
        frame=self.frame()
        self.current={**frame,'id':secrets.token_hex(16),'created':time.monotonic()}
        return {'observation_id':self.current['id'],'width_px':frame['pixels'][0],
                'height_px':frame['pixels'][1],'coordinates':'normalized full-screen bounding box',
                'expires_in_seconds':45}

    def image(self):
        return self.current['png'] if self.current else None

    def tap(self, observation_id, box):
        previous=self.current
        if not previous or previous['id']!=observation_id:
            return {'ok':False,'reason':'stale_visual_observation'}
        if time.monotonic()-previous['created']>45:
            self.invalidate();return {'ok':False,'reason':'expired_visual_observation'}
        x1,y1,x2,y2=box
        if not (0<=x1<x2<=1 and 0<=y1<y2<=1):
            return {'ok':False,'reason':'invalid_visual_box'}
        current=self.frame()
        if any(current[k]!=previous[k] for k in ('size','orientation','pixels','layout')):
            self.invalidate();return {'ok':False,'reason':'screen_layout_changed'}
        if not stable_target(previous,current,box):
            self.invalidate();return {'ok':False,'reason':'target_region_changed'}
        self.invalidate() # Consume before attempting a mutation; never replay an uncertain tap.
        self.phone.execute({'action':'tap','x':(x1+x2)/2,'y':(y1+y2)/2})
        return {'ok':True}
