"""Select complete, useful screen records from the whole tree, never an XML prefix."""
import json
import math
import re
import xml.etree.ElementTree as ET

INPUTS={'XCUIElementTypeTextField','XCUIElementTypeSearchField','XCUIElementTypeTextView',
        'XCUIElementTypeSecureTextField'}
CONTROLS=INPUTS|{'XCUIElementTypeButton','XCUIElementTypeLink','XCUIElementTypeCell',
    'XCUIElementTypeSwitch','XCUIElementTypeSlider','XCUIElementTypePickerWheel'}
LAYOUT={'XCUIElementTypeOther','XCUIElementTypeWindow','XCUIElementTypeScrollView',
        'XCUIElementTypeCollectionView','XCUIElementTypeTable'}
STOP=set('the and for with from that this then only task user current phone app use one best '
         'available based visible evidence verify report before after requested exactly stop '
         'not any other its into through when will can should would have has been are was '
         'add select find give briefly explain do to in of a an or on my at it is'.split())


def terms(task):
    return set(token for token in re.findall(r'\w+(?:\.\d+)?',task.casefold())
               if token not in STOP and (len(token)>2 or any(c.isdigit() for c in token)))


def rect(attrs):
    source=attrs.get('rect',attrs)
    try:
        result={key:float(source[key]) for key in ('x','y','width','height')}
        if not all(math.isfinite(value) for value in result.values()):return None
        if result['width']<=0 or result['height']<=0:return None
        return result
    except (KeyError,TypeError,ValueError):return None


def intersects(bounds,viewport):
    if not bounds or not viewport:return None
    return (bounds['x']<viewport['x']+viewport['width'] and
            bounds['y']<viewport['y']+viewport['height'] and
            bounds['x']+bounds['width']>viewport['x'] and
            bounds['y']+bounds['height']>viewport['y'])


def priority(attrs,task_terms,viewport=None):
    kind=attrs.get('type','');bounds=rect(attrs);inside=intersects(bounds,viewport)
    text=' '.join(str(attrs.get(key,'') or '') for key in ('name','label','value')).casefold()
    matches=sum(term in text for term in task_terms)
    score=(60 if kind in CONTROLS else 30)+min(matches,8)*12
    if inside is True:score+=30
    elif inside is False:score-=150
    if str(attrs.get('enabled','true')).casefold()=='false':score-=45
    if str(attrs.get('visible','true')).casefold()=='false':score-=300
    if re.search(r'\b(results|filter|size|cart|search|rating|price)\b',text):score+=15
    return score


def summarize(value,limit=20000,task='',viewport=None):
    if isinstance(limit,bool) or not isinstance(limit,int) or limit<256:
        raise ValueError('Screen character budget must be an integer of at least 256')
    root=ET.fromstring(value['source'])
    all_nodes=list(root.iter())
    if viewport is None:
        # The application frame is in WDA logical coordinates, not screenshot pixels.
        viewport=next((rect(node.attrib) for node in all_nodes
            if node.attrib.get('type',node.tag)=='XCUIElementTypeApplication' and rect(node.attrib)),None)
    records=[];seen=set();counts={'layout':0,'duplicate':0,'hidden':0,'input_descendants':0}
    task_terms=terms(task)
    def visit(node,depth,input_parent=False,hidden_parent=False):
        kind=node.attrib.get('type',node.tag)
        if input_parent:
            counts['input_descendants']+=1
            for child in node:visit(child,depth+1,True)
            return
        attrs={key:val for key,val in node.attrib.items() if key in
            ('name','label','value','enabled','visible','x','y','width','height')}
        attrs['type']=kind
        if kind=='XCUIElementTypeSecureTextField':attrs.pop('value',None)
        hidden=hidden_parent or str(attrs.get('visible','')).casefold()=='false'
        if hidden:
            counts['hidden']+=1
        elif len(node) and kind in LAYOUT:
            # Container labels often concatenate hundreds of descendant labels.
            # Their real child records remain independently eligible for selection.
            counts['layout']+=1
        else:
            if attrs.get('label')==attrs.get('name'):attrs.pop('label',None)
            if attrs.get('value')==attrs.get('name') and kind not in INPUTS:attrs.pop('value',None)
            if any(attrs.get(key) for key in ('name','label','value')) or kind in CONTROLS or kind=='XCUIElementTypeApplication':
                for key in ('name','label','value'):
                    text=attrs.get(key)
                    if isinstance(text,str) and len(text)>500:
                        attrs[key]=text[:497]+'...';attrs['text_clipped']=True
                signature=json.dumps(attrs,sort_keys=True,ensure_ascii=False)
                if signature in seen:counts['duplicate']+=1
                else:
                    seen.add(signature)
                    line=' '*min(depth,60)+json.dumps(attrs,ensure_ascii=False,separators=(',',':'))
                    bounds=rect(attrs)
                    inside=intersects(bounds,viewport)
                    band=4
                    if bounds and viewport and inside:
                        center=(bounds['y']+min(bounds['height'],viewport['height'])/2-viewport['y'])/viewport['height']
                        band=max(0,min(3,int(center*4)))
                    records.append({'line':line,'index':len(records),'score':priority(attrs,task_terms,viewport),
                        'band':band,'offscreen':inside is False,'kind':kind})
        for child in node:visit(child,depth+1,kind in INPUTS,hidden)
    visit(root,0)
    # Round-robin viewport bands prevent an early banner/container from consuming the
    # budget before a filter or results heading near the bottom is considered.
    bands={key:[] for key in range(5)}
    for item in records:bands[item['band']].append(item)
    for group in bands.values():group.sort(key=lambda item:(-item['score'],item['index']))
    selected=[];used=0;offscreen_used=0
    while any(bands.values()):
        for band in range(5):
            if not bands[band]:continue
            item=bands[band].pop(0);cost=len(item['line'])+bool(selected)
            if used+cost>limit:continue
            if item['offscreen'] and offscreen_used+cost>limit//10:continue
            selected.append(item);used+=cost
            if item['offscreen']:offscreen_used+=cost
    selected.sort(key=lambda item:item['index'])
    text='\n'.join(item['line'] for item in selected)
    return {'tree':text,'nodes':len(all_nodes),'selected_nodes':len(selected),
        'truncated':len(selected)<len(records),'selection':'whole_tree_viewport_and_task_priority',
        'omitted':{**counts,'budget':len(records)-len(selected)},
        'viewport':viewport,'excluded_attributes':value.get('excluded_attributes',[]),
        'warning':'Screen records are selected from the whole accessibility tree. Bounds intersecting the viewport do not prove visibility or lack of overlays. Verify targets before acting; clipped text is not an exact selector.'}
