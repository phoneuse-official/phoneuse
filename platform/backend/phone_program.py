"""Bounded declarative phone programs; never executes model-supplied code."""
import json
import time
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .targeting import Target, INPUT_TYPES, CONTROL_TYPES
from .usb import DeviceError
from .screen_observation import priority, terms

class Step(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['launch_app', 'home', 'click_target', 'wait_target', 'read_page', 'fill_field', 'submit_search', 'focus_search', 'search', 'visual_tap']
    target: Target | None = None
    editor: Target | None = None
    observation_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    box: tuple[float,float,float,float] | None = None
    verify: Literal['page','editor'] = 'page'
    query: str | None = Field(default=None, min_length=1, max_length=500)
    bundle_id: str | None = Field(default=None, pattern=r'^[A-Za-z0-9][A-Za-z0-9._-]{1,249}$')
    timeout_ms: int = Field(default=4000, ge=0, le=8000)
    text: str | None = Field(default=None,min_length=1,max_length=2000)
    expected: str | None = Field(default=None,min_length=1,max_length=500)
    @model_validator(mode='after')
    def required(self):
        if self.action in ('click_target','wait_target','fill_field','submit_search','focus_search','search') and not (self.query or self.target):
            raise ValueError('Target name required')
        if self.action == 'launch_app' and not self.bundle_id:
            raise ValueError('Bundle ID required')
        if self.action in ('fill_field','submit_search','search') and (
            not self.text or any(ord(c)<32 or ord(c)==127 for c in self.text)):
            raise ValueError('Nonempty single-line text required')
        if (self.action in ('submit_search','search') or (self.action=='visual_tap' and self.verify=='page')) and not self.expected:
            raise ValueError('Expected result text required before submitting a search')
        if self.action=='visual_tap':
            if not self.observation_id or not self.box:
                raise ValueError('Visual tap requires an observation and normalized target box')
            x1,y1,x2,y2=self.box
            if not (0<=x1<x2<=1 and 0<=y1<y2<=1):
                raise ValueError('Visual target box must be inside the screenshot')
        return self

class Program(BaseModel):
    model_config = ConfigDict(extra='forbid')
    steps: list[Step] = Field(min_length=1, max_length=8)

TOOL = {'name':'phone_program', 'description':
    'Execute up to 8 conditional task steps locally. Each named target must uniquely exist and be visible/enabled before clicking. Stops on an unmet condition. Returns the final page. Consequential actions require explicit authorization in the current user task.',
    'input_schema':Program.model_json_schema()}

GUIDANCE = '''Prefer phone_program for predictable navigation to reduce model round trips.
Steps are launch_app(bundle_id), home, click_target(query), wait_target(query), read_page,
fill_field(query,text), submit_search(query,text,expected), focus_search(query,editor),
search(query,text,expected,editor), and visual_tap(observation_id,box,expected).
Use target={identifier,label,type,within:{identifier,label,type},strategy} for precise native matching.
strategy defaults to predicate; class_chain is also supported.
Use target={ref} for a current page target reference; references expire after screen changes.
query is a label fallback. Each click is checked locally. Scope duplicate labels to a container.
search performs focus, verified fill, submit, and expected-result verification in one program.
focus_search first tries an editor, then clicks the search/address control once and resolves
its newly revealed editor. editor optionally identifies that editor precisely.
A definitive missing, ambiguous, or unsupported target returns immediately; only wait_target polls.
After a native targeting failure, an enabled visual fallback may supply a screenshot and
visual observation ID. Use visual_tap with a normalized bounding box [left,top,right,bottom]
from that screenshot and expected visible result text. Never invent an observation or coordinates.
For search/address controls use visual_tap with verify=editor to verify focused input;
otherwise supply expected page text. Visual taps stop if the screenshot changed or expired. A tap is never replayed automatically.
Use known app navigation labels or observed labels; a missing/ambiguous target stops the program.
Do not run a chain whose next action needs interpretation of the preceding result.
An unmet condition returns needs_replan and a fresh page. Re-plan from that page.
A hidden or disabled target is not evidence that it obscures the screen. Ignore irrelevant
failed controls and use current task-relevant targets, scroll, or an authorized alternate route.
Screen records are selected across the complete tree; text_clipped labels are not exact selectors.
A failed mutation stops the task; never replay it. Read the returned page before reporting results.
click_target automatically finds the target, verifies it, clicks once, and returns a fresh page.
Do not spend separate decisions finding elements, checking state, or reading after a program.
Every program returns its final page automatically; do not append a redundant read_page.
Use read_page alone for an initial observation. Use launch_app directly for a requested installed app.
Never use global text typing. fill_field targets an observed ordinary editable field,
replaces its content once and verifies the exact value. It never submits.
submit_search verifies the field still contains text, submits once, then waits for expected
result text to appear on a changed page. expected must describe the next screen, not a label
already present. For browser navigation, expect a destination heading or title rendered
outside input fields. Use the requested domain only if the page content exposes it;
address-bar text alone is not navigation evidence. Then search on that site.
An unverified mutation returns uncertain: stop, do not replay or claim success.
needs_replan means no uncertain mutation occurred: inspect the fresh page, correct the target
or dismiss an observed overlay, and try a different justified plan. At most two recovery attempts.
Define success from the user's request; verify the destination and actual search results before finish.
Swipes also return a fresh page automatically.
'''

def semantic_page(page):
    """Ignore geometry and enabled-state noise when checking navigation progress."""
    rows=[];keyboard_depth=None
    for line in page.get('tree','').splitlines():
        try:
            attrs=json.loads(line)
            depth=len(line)-len(line.lstrip())
            if keyboard_depth is not None:
                if depth>keyboard_depth:continue
                keyboard_depth=None
            kind=attrs.get('type','')
            if kind in ('XCUIElementTypeKeyboard','XCUIElementTypeTextField','XCUIElementTypeSearchField','XCUIElementTypeTextView','XCUIElementTypeSecureTextField'):
                keyboard_depth=depth;continue
            if kind=='XCUIElementTypeKey':continue
            rows.append({k:v for k,v in attrs.items() if k in ('type','name','label','value')})
        except (ValueError,AttributeError):rows.append(line)
    return rows

def handle(candidate):
    return {key:candidate[key] for key in ('session_id','element_id')}


def resolve(phone, step, input_step=False, target=None):
    target=target or step.target
    if target and target.ref:
        refs=getattr(phone,'target_refs',None)
        candidate=refs.get(target.ref) if refs else None
        if not candidate:return None,'stale_reference'
        # A cached handle is usable only while its observed screen remains current.
        page=phone.execute({'action':'source_fast'})
        if semantic_page(page)!=getattr(phone,'target_page',None):
            refs.invalidate()
            return None,'stale_reference'
        found={'elements':[candidate],'count':1}
    else:
        params={'action':'find_elements'}
        if target:params['target']=target.model_dump(exclude_none=True)
        elif input_step:params['target']={'label':step.query,'types':list(INPUT_TYPES)}
        else:params['query']=step.query
        found=phone.execute(params)
    if found.get('reason') in ('container_missing','container_ambiguous'):
        return None,found['reason']
    if not found['count']:return None,'missing'
    if found['count']>12:return None,'ambiguous'
    eligible=[];reason='hidden_or_disabled'
    for candidate in found['elements']:
        attrs=candidate.get('attributes',{})
        state=attrs if 'displayed' in attrs and 'enabled' in attrs else phone.execute(
            {'action':'element_state',**handle(candidate)})
        if state.get('displayed') is not True or state.get('enabled') is not True:continue
        if input_step:
            if 'type' in attrs:
                if attrs['type'] not in INPUT_TYPES:
                    reason='unsupported_input_type';continue
            else:
                probe=phone.execute({'action':'element_input_state',**handle(candidate)})
                if not probe.get('eligible'):
                    reason='unsupported_input_type';continue
        eligible.append(candidate)
    if len(eligible)>1:return None,'ambiguous'
    return (eligible[0],None) if eligible else (None,reason)


def active_editor(phone):
    if not getattr(phone,'supports_active_element',False):return None
    candidate=phone.execute({'action':'active_element'})
    if not candidate:return None
    attrs=candidate.get('attributes',{})
    if attrs.get('type') in INPUT_TYPES and attrs.get('displayed') is True and attrs.get('enabled') is True:
        return candidate
    if phone.execute({'action':'element_input_state',**handle(candidate)}).get('eligible'):
        return candidate
    return None


def focus_editor(phone, step):
    target,reason=resolve(phone,step,input_step=True,target=step.editor)
    if target or reason not in ('missing','unsupported_input_type'):return target,reason
    control,reason=resolve(phone,step)
    if not control:return None,reason
    phone.execute({'action':'element_click',**handle(control)})
    # Prefer XCTest's actual focused editor over guessing among multiple page fields.
    focused=active_editor(phone)
    if step.editor:
        # Focus can land in an unrelated field. An explicit selector remains a
        # constraint after the transition, rather than a hint we can discard.
        target,reason=resolve(phone,step,input_step=True,target=step.editor)
        if not target:return None,reason
        if focused and handle(focused)!=handle(target):
            return None,'focused_editor_mismatch'
        return target,None
    if focused:return focused,None
    # A focus transition invalidates earlier target references and may create a new field.
    for editor in ([step.editor] if step.editor else [Target(type=kind) for kind in INPUT_TYPES]):
        target,reason=resolve(phone,step,input_step=True,target=editor)
        if target:return target,None
        if reason=='ambiguous':return None,reason
    return None,'editor_not_found_after_focus'


def observe(phone):
    page=phone.execute({'action':'source_fast'})
    if getattr(phone,'rich_targets',False):
        refs=phone.target_refs
        refs.invalidate()
        targets=[]
        # Discovery is capped by control class; do not read input values into target metadata.
        found=phone.execute({'action':'find_elements','target':{'types':list(CONTROL_TYPES)}})
        candidates=[item for item in found['elements'] if item.get('attributes',{}).get('displayed') is True
            and item.get('attributes',{}).get('enabled') is True]
        task_terms=terms(getattr(phone,'task_text',''))
        candidates.sort(key=lambda item:-priority(item['attributes'],task_terms,page.get('viewport')))
        for candidate in candidates[:32]:
            attrs=dict(candidate['attributes'])
            # Do not turn a long aggregate accessibility name into a guessed exact selector.
            for key in ('name','label'):
                if isinstance(attrs.get(key),str) and len(attrs[key])>500:
                    attrs[key]=attrs[key][:497]+'...';attrs['text_clipped']=True
            targets.append({'ref':refs.add(candidate),**attrs})
        phone.target_page=semantic_page(page)
        page={**page,'targets':targets,'revision':refs.revision}
    return page


def capture_visual(phone):
    vision=getattr(phone,'vision',None)
    if not vision:return None
    try:return vision.capture()
    except PermissionError:raise
    except (ValueError,OSError,DeviceError):
        vision.invalidate()
        return {'available':False,'reason':'capture_failed'}


def recovery_observation(phone):
    result={'page':observe(phone),'recovery_review':True,
        'guidance':'Review this fresh screen before declaring blocked. A hidden/disabled control is not proof of an obstructing panel. Prefer another visible task-relevant control, scroll when justified, or use an authorized alternate route. Use the screenshot if supplied. Do not replay uncertain mutations or change the task constraints.'}
    visual=capture_visual(phone)
    if visual is not None:result['visual']=visual
    return result


def verify_destination(phone, before, expected, timeout_ms):
    deadline=time.monotonic()+timeout_ms/1000
    while True:
        page=phone.execute({'action':'source_fast'})
        evidence=json.dumps(semantic_page(page),ensure_ascii=False)
        if semantic_page(page)!=semantic_page(before) and expected.casefold() in evidence.casefold():
            return page,True
        if time.monotonic()>=deadline:return page,False
        time.sleep(.2)


def execute(phone, params, progress=lambda **kw:None, available_apps=None):
    program=Program.model_validate(params) # Validate the entire plan before touching a phone.
    if available_apps is not None and any(step.action=='launch_app' and step.bundle_id not in available_apps for step in program.steps):
        return {'status':'needs_replan','steps':[{'action':'launch_app','ok':False,
            'reason':'App ID is not in the installed-app inventory; use a listed app or the installed browser for a website'}],
            'page':phone.execute({'action':'source_fast'})}
    steps=[];status='completed';started=time.monotonic();page=None
    for index,step in enumerate(program.steps):
        page=None
        if time.monotonic()-started>45:
            status='needs_replan';break
        t=time.monotonic()
        progress(stage='device',current_action=step.action,program_step=index+1,program_total=len(program.steps))
        if step.action=='visual_tap':
            vision=getattr(phone,'vision',None)
            if not vision:
                status='needs_replan';steps.append({'action':step.action,'ok':False,'reason':'visual_disabled'});break
            before=phone.execute({'action':'source_fast'})
            if step.verify=='page' and step.expected.casefold() in json.dumps(semantic_page(before),ensure_ascii=False).casefold():
                status='needs_replan';steps.append({'action':step.action,'ok':False,'reason':'Expected text already present'});break
            result=vision.tap(step.observation_id,step.box)
            if not result['ok']:
                status='needs_replan';steps.append({'action':step.action,'ok':False,'reason':result['reason']});break
            if step.verify=='editor':
                focused=active_editor(phone)
                verified=focused is not None
                page=phone.execute({'action':'source_fast'})
                if verified and getattr(phone,'target_refs',None):
                    phone.target_page=semantic_page(page)
                    page={**page,'targets':[{'ref':phone.target_refs.add(focused),**focused.get('attributes',{})}]}
            else:page,verified=verify_destination(phone,before,step.expected,step.timeout_ms)
            if not verified:
                status='uncertain';steps.append({'action':step.action,'ok':False,'reason':'Tapped once but result not verified; do not replay'});break
        elif step.action in ('click_target','wait_target','fill_field','submit_search','focus_search','search'):
            input_step=step.action in ('fill_field','submit_search')
            deadline=t+step.timeout_ms/1000
            while True:
                target,reason=focus_editor(phone,step) if step.action in ('focus_search','search') else resolve(phone,step,input_step)
                if target or step.action!='wait_target' or reason not in ('missing','hidden_or_disabled') or time.monotonic()>=deadline:break
                time.sleep(.15)
            if target is None:
                steps.append({'action':step.action,'ok':False,'reason':reason,'seconds':round(time.monotonic()-t,3)})
                status='needs_replan';break
            if step.action=='click_target':phone.execute({'action':'element_click',**handle(target)})
            elif step.action in ('fill_field','submit_search','search'):
                submitting=step.action in ('submit_search','search')
                before=phone.execute({'action':'source_fast'}) if submitting else None
                if before is not None and step.expected.casefold() in json.dumps(semantic_page(before),ensure_ascii=False).casefold():
                    status='needs_replan';page=before
                    steps.append({'action':step.action,'ok':False,'reason':'Expected text is already present; choose new destination evidence before submitting'});break
                if step.action in ('fill_field','search'):
                    result=phone.execute({'action':'element_fill',**handle(target),'text':step.text})
                    if result.get('status')!='completed':
                        status=result.get('status','uncertain')
                        steps.append({'action':step.action,'ok':False,'reason':result.get('reason','Input outcome uncertain')});break
                    if result.get('handle'):target=result['handle']
                    # Verified entry is progress even if a later submit precondition fails.
                    if step.action=='search':steps.append({'action':'fill_field','ok':True})
                if submitting:
                    result=phone.execute({'action':'element_submit_search',**handle(target),'text':step.text})
                    if result.get('status')!='submitted':
                        status=result.get('status','uncertain')
                        steps.append({'action':step.action,'ok':False,'reason':result.get('reason','Submission outcome uncertain')});break
                    page,verified=verify_destination(phone,before,step.expected,step.timeout_ms)
                    if not verified:
                        status='uncertain';steps.append({'action':step.action,'ok':False,
                            'reason':'Submitted once, but expected destination was not verified; do not resubmit'});break
        elif step.action=='read_page':pass
        else:phone.execute({'action':step.action,**({'bundle_id':step.bundle_id} if step.bundle_id else {})})
        steps.append({'action':step.action,'ok':True,'seconds':round(time.monotonic()-t,3)})
        if step.action not in ('submit_search','search','visual_tap'):page=None
    # Avoid adding discovery work to every click: inventories are requested by read_page.
    if page is None:
        page=observe(phone) if program.steps[-1].action=='read_page' and status=='completed' else phone.execute({'action':'source_fast'})
    result={'status':status,'steps':steps,'page':page}
    if status=='needs_replan':
        result['guidance']='The failed target is unavailable; this does not prove that a panel blocks the screen. Choose another justified current target or route. Never replay an uncertain mutation.'
        visual=capture_visual(phone)
        if visual is not None:result['visual']=visual
    return result
