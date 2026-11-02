"""Bounded declarative phone programs; never executes model-supplied code."""
import json
import time
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class Step(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['launch_app', 'home', 'click_target', 'wait_target', 'read_page', 'fill_field', 'submit_search']
    query: str | None = Field(default=None, min_length=1, max_length=500)
    bundle_id: str | None = Field(default=None, pattern=r'^[A-Za-z0-9][A-Za-z0-9._-]{1,249}$')
    timeout_ms: int = Field(default=4000, ge=0, le=8000)
    text: str | None = Field(default=None,min_length=1,max_length=2000)
    expected: str | None = Field(default=None,min_length=1,max_length=500)
    @model_validator(mode='after')
    def required(self):
        if self.action in ('click_target','wait_target','fill_field','submit_search') and not self.query:
            raise ValueError('Target name required')
        if self.action == 'launch_app' and not self.bundle_id:
            raise ValueError('Bundle ID required')
        if self.action in ('fill_field','submit_search') and (
            not self.text or any(ord(c)<32 or ord(c)==127 for c in self.text)):
            raise ValueError('Nonempty single-line text required')
        if self.action=='submit_search' and not self.expected:
            raise ValueError('Expected result text required before submitting a search')
        return self

class Program(BaseModel):
    model_config = ConfigDict(extra='forbid')
    steps: list[Step] = Field(min_length=1, max_length=8)

TOOL = {'name':'phone_program', 'description':
    'Execute up to 8 conditional navigation steps locally. Each named target must uniquely exist and be visible/enabled before clicking. Stops on an unmet condition. Returns the final page. Use for predictable navigation, never for sending, buying, deleting, or changing settings.',
    'input_schema':Program.model_json_schema()}

GUIDANCE = '''Prefer phone_program for predictable navigation to reduce model round trips.
Steps are launch_app(bundle_id), home, click_target(query), wait_target(query), read_page,
fill_field(query,text), submit_search(query,text,expected).
query is an exact accessibility name, never a coordinate. Each click is checked locally.
Use known app navigation labels or observed labels; a missing/ambiguous target stops the program.
Do not run a chain whose next action needs interpretation of the preceding result.
An unmet condition returns needs_replan and a fresh page. Re-plan from that page.
A failed mutation stops the task; never replay it. Read the returned page before reporting results.
click_target automatically finds the target, verifies it, clicks once, and returns a fresh page.
Do not spend separate decisions finding elements, checking state, or reading after a program.
Every program returns its final page automatically; do not append a redundant read_page.
Use read_page alone for an initial observation. Use launch_app directly for a requested installed app.
Never use global text typing. fill_field targets an observed ordinary single-line field,
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
            if kind=='XCUIElementTypeKeyboard':
                keyboard_depth=depth;continue
            if kind in ('XCUIElementTypeTextField','XCUIElementTypeSearchField','XCUIElementTypeSecureTextField','XCUIElementTypeKey'):continue
            rows.append({k:v for k,v in attrs.items() if k in ('type','name','label','value')})
        except (ValueError,AttributeError):rows.append(line)
    return rows

def execute(phone, params, progress=lambda **kw:None, available_apps=None):
    program = Program.model_validate(params) # Validate the entire plan before touching a phone.
    if available_apps is not None and any(step.action=='launch_app' and step.bundle_id not in available_apps for step in program.steps):
        return {'status':'needs_replan','steps':[{'action':'launch_app','ok':False,
            'reason':'App ID is not in the installed-app inventory; use a listed app or the installed browser for a website'}],
            'page':phone.execute({'action':'source_fast'})}
    steps=[]; status='completed'; started=time.monotonic();page=None
    for index, step in enumerate(program.steps):
        page=None
        if time.monotonic()-started > 45:
            status='needs_replan'; break
        t=time.monotonic()
        progress(stage='device', current_action=step.action, program_step=index+1, program_total=len(program.steps))
        if step.action in ('click_target','wait_target','fill_field','submit_search'):
            deadline=t+step.timeout_ms/1000
            target=None;input_state=None
            input_step=step.action in ('fill_field','submit_search')
            while True:
                found=phone.execute({'action':'find_elements','query':step.query})
                candidates=found['elements'] if input_step and found['count']<=12 else (
                    found['elements'] if found['count']==1 else [])
                eligible=[]
                for candidate in candidates:
                    state=phone.execute({'action':'element_state',**candidate})
                    if state.get('displayed') is True and state.get('enabled') is True:
                        probe=phone.execute({'action':'element_input_state',**candidate}) if input_step else None
                        if not input_step or probe.get('eligible'):
                            eligible.append((candidate,probe))
                if len(eligible)==1:
                    target,input_state=eligible[0];break
                if len(eligible)>1 or found['count']>12 or (not input_step and found['count']>1) or time.monotonic()>=deadline:break
                time.sleep(.15)
            if target is None:
                steps.append({'action':step.action,'ok':False,'reason':'Target missing, ambiguous or not interactable','seconds':round(time.monotonic()-t,3)})
                status='needs_replan';break
            if step.action=='click_target':
                phone.execute({'action':'element_click',**target})
            elif step.action in ('fill_field','submit_search'):
                state=input_state
                if not state.get('eligible'):
                    steps.append({'action':step.action,'ok':False,'reason':state.get('reason','Input is not interactable')})
                    status='needs_replan';break
                before=phone.execute({'action':'source_fast'}) if step.action=='submit_search' else None
                if before is not None and step.expected.casefold() in json.dumps(semantic_page(before),ensure_ascii=False).casefold():
                    status='needs_replan';page=before
                    steps.append({'action':step.action,'ok':False,
                        'reason':'Expected text is already present; choose new destination evidence before submitting'})
                    break
                result=phone.execute({'action':'element_fill' if step.action=='fill_field' else 'element_submit_search',
                    **target,'text':step.text})
                if result.get('status') not in ('completed','submitted'):
                    status=result.get('status','uncertain')
                    steps.append({'action':step.action,'ok':False,'reason':result.get('reason','Input outcome uncertain')})
                    break
                if step.action=='submit_search':
                    deadline=time.monotonic()+step.timeout_ms/1000
                    while True:
                        page=phone.execute({'action':'source_fast'})
                        evidence=json.dumps(semantic_page(page),ensure_ascii=False)
                        if semantic_page(page)!=semantic_page(before) and step.expected.casefold() in evidence.casefold():
                            break
                        if time.monotonic()>=deadline:
                            status='uncertain'
                            steps.append({'action':step.action,'ok':False,'reason':'Submitted once, but expected destination was not verified; do not resubmit'})
                            break
                        time.sleep(.2)
                    if status=='uncertain':break
        elif step.action=='read_page':
            pass # A fresh page is always returned below.
        else:
            phone.execute({'action':step.action,**({'bundle_id':step.bundle_id} if step.bundle_id else {})})
        steps.append({'action':step.action,'ok':True,'seconds':round(time.monotonic()-t,3)})
        # Any later step invalidates a cached observation from submission.
        if step.action!='submit_search':page=None
    return {'status':status,'steps':steps,'page':page if page is not None else phone.execute({'action':'source_fast'})}
