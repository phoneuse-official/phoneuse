"""Local, conservative template matching for a small set of toolbar icons.

Candidates are visual hypotheses, not proof that a control is tappable.
"""
import io
import json
from PIL import Image, ImageDraw
from .screen_observation import rect

KINDS=('back','close','menu','search')


def templates(size=32):
    patterns={}
    for kind in KINDS:
        im=Image.new('1',(size,size)); d=ImageDraw.Draw(im); width=3
        if kind=='back':
            d.line([(21,5),(9,16),(21,27)],fill=1,width=width,joint='curve')
        elif kind=='close':
            d.line([(7,7),(25,25)],fill=1,width=width);d.line([(25,7),(7,25)],fill=1,width=width)
        elif kind=='menu':
            for y in (7,16,25):d.line([(5,y),(27,y)],fill=1,width=width)
        else:
            d.ellipse((5,4,21,20),outline=1,width=width);d.line([(19,19),(27,27)],fill=1,width=width)
        patterns[kind]=im
    return patterns


def normalized(mask):
    bbox=mask.getbbox()
    if not bbox:return None
    inner=mask.crop(bbox).resize((24,24),Image.Resampling.NEAREST)
    out=Image.new('1',(32,32));out.paste(inner,(4,4));return out


def score(mask,pattern):
    a=normalized(mask);b=normalized(pattern)
    if not a or not b:return 0.0
    # Dilated overlap tolerates antialiasing, stroke width and scale differences.
    from PIL import ImageFilter, ImageChops
    aa=a.convert('L');bb=b.convert('L')
    ad=aa.filter(ImageFilter.MaxFilter(5));bd=bb.filter(ImageFilter.MaxFilter(5))
    ac=sum(v>0 for v in aa.get_flattened_data());bc=sum(v>0 for v in bb.get_flattened_data())
    if not ac or not bc:return 0.0
    p=sum(v>0 for v in ImageChops.logical_and(a,bd.convert('1')).get_flattened_data())/ac
    r=sum(v>0 for v in ImageChops.logical_and(b,ad.convert('1')).get_flattened_data())/bc
    return 2*p*r/(p+r) if p+r else 0.0


def detect(image, ocr_lines=()):
    original=Image.open(io.BytesIO(image)).convert('RGB'); w,h=original.size
    small=original.resize((320,round(h*320/w)),Image.Resampling.LANCZOS)
    sw,sh=small.size; gray=small.convert('L');pix=gray.load(); patterns=templates()
    results=[]
    # Search only in chrome near top/bottom edges; avoid treating page text as icons.
    regions=[(0,0,sw,int(sh*.18)),(0,int(sh*.82),sw,sh)]
    occupied=[r['box'] for r in ocr_lines]
    for x0,y0,xend,yend in regions:
        for polarity in ('dark','light'):
            seen=set();components=[]
            def foreground(x,y):return pix[x,y]<100 if polarity=='dark' else pix[x,y]>155
            for y in range(y0,yend):
                for x in range(x0,xend):
                    if (x,y) in seen or not foreground(x,y):continue
                    seen.add((x,y));stack=[(x,y)];pts=[]
                    while stack:
                        px,py=stack.pop();pts.append((px,py))
                        for nx,ny in ((px-1,py),(px+1,py),(px,py-1),(px,py+1),
                                      (px-1,py-1),(px+1,py-1),(px-1,py+1),(px+1,py+1)):
                            if x0<=nx<xend and y0<=ny<yend and (nx,ny) not in seen and foreground(nx,ny):
                                seen.add((nx,ny));stack.append((nx,ny))
                    if 5<=len(pts)<=500:
                        xs=[p[0] for p in pts];ys=[p[1] for p in pts]
                        box=(min(xs),min(ys),max(xs)+1,max(ys)+1)
                        if 4<=box[2]-box[0]<=35 and 1<=box[3]-box[1]<=35:components.append(box)
            # Three disconnected horizontal bars form the menu icon.
            for a in list(components):
                bars=[b for b in components if abs(b[0]-a[0])<=2 and abs(b[2]-a[2])<=2
                      and abs(b[1]-a[1])<=20 and b[2]-b[0]>=10 and b[3]-b[1]<=5]
                if len(bars)==3:
                    components.append((min(b[0] for b in bars),min(b[1] for b in bars),
                                       max(b[2] for b in bars),max(b[3] for b in bars)))
            for box in components:
                x1,y1,x2,y2=box
                if min(x2-x1,y2-y1)<6:continue
                if not (x1<sw*.22 or x2>sw*.78):continue
                norm=(x1/sw,y1/sh,x2/sw,y2/sh)
                if any(not (norm[2]<b[0] or norm[0]>b[2] or norm[3]<b[1] or norm[1]>b[3]) for b in occupied):continue
                # Reject low-contrast background components and recognize only compact shapes.
                if (x2-x1)*(y2-y1)<45:continue
                mask=Image.new('1',(x2-x1,y2-y1));mp=mask.load()
                for yy in range(y1,y2):
                    for xx in range(x1,x2):mp[xx-x1,yy-y1]=foreground(xx,yy)
                matches=sorted(((score(mask,p),k) for k,p in patterns.items()),reverse=True)
                confidence,kind=matches[0]
                if confidence<.82 or confidence-matches[1][0]<.04:continue
                results.append({'kind':kind,'confidence':round(confidence,3),'box':[round(v,6) for v in norm],
                                'source':'template','verified':False})
    results.sort(key=lambda r:-r['confidence'])
    unique=[]
    for candidate in results:
        a=candidate['box']
        if any(abs((a[0]+a[2]-b['box'][0]-b['box'][2])/2)<.025 and abs((a[1]+a[3]-b['box'][1]-b['box'][3])/2)<.012 for b in unique):continue
        cx=(a[0]+a[2])/2;cy=(a[1]+a[3])/2
        nearby=[]
        for row in ocr_lines:
            b=row['box'];distance=((cx-(b[0]+b[2])/2)**2+(cy-(b[1]+b[3])/2)**2)**.5
            if distance<.12:nearby.append((distance,row.get('text','')))
        candidate['nearby_text']=[text[:120] for _,text in sorted(nearby)[:2] if text]
        candidate['id']='icon-'+str(len(unique));unique.append(candidate)
        if len(unique)>=12:break
    return unique


def attach_accessibility(candidates, page, viewport):
    """Attach a unique overlapping native label as an additional, unverified cue."""
    entries=[]
    for line in page.get('tree','').splitlines():
        try: item=json.loads(line)
        except (ValueError,TypeError):continue
        bounds=rect(item);label=item.get('name') or item.get('label')
        if bounds and label and item.get('type') not in ('XCUIElementTypeSecureTextField','XCUIElementTypeTextField','XCUIElementTypeTextView'):
            entries.append((bounds,str(label)[:200],item.get('type','')))
    result=[]
    for icon in candidates:
        x1,y1,x2,y2=icon['box'];cx=(x1+x2)/2*viewport['width'];cy=(y1+y2)/2*viewport['height']
        matches=[(label,kind) for b,label,kind in entries if b['x']<=cx<=b['x']+b['width'] and b['y']<=cy<=b['y']+b['height']]
        enriched=dict(icon)
        if len(matches)==1:enriched['accessibility']={'label':matches[0][0],'type':matches[0][1]}
        result.append(enriched)
    return result
