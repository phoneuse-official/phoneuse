"""Bounded declarative phone programs; never executes model-supplied code."""
import time
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

class Step(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['launch_app', 'home', 'click_target', 'wait_target', 'read_page']
    query: str | None = Field(default=None, min_length=1, max_length=500)
    bundle_id: str | None = Field(default=None, pattern=r'^[A-Za-z0-9][A-Za-z0-9._-]{1,249}$')
    timeout_ms: int = Field(default=4000, ge=0, le=8000)
    @model_validator(mode='after')
    def required(self):
        if self.action in ('click_target','wait_target') and not self.query:
            raise ValueError('Target name required')
        if self.action == 'launch_app' and not self.bundle_id:
            raise ValueError('Bundle ID required')
        return self

class Program(BaseModel):
    model_config = ConfigDict(extra='forbid')
    steps: list[Step] = Field(min_length=1, max_length=8)

TOOL = {'name':'phone_program', 'description':
    'Execute up to 8 conditional navigation steps locally. Each named target must uniquely exist and be visible/enabled before clicking. Stops on an unmet condition. Returns the final page. Use for predictable navigation, never for sending, buying, deleting, or changing settings.',
    'input_schema':Program.model_json_schema()}

GUIDANCE = '''Prefer phone_program for predictable navigation to reduce model round trips.
Steps are launch_app(bundle_id), home, click_target(query), wait_target(query), read_page.
query is an exact accessibility name, never a coordinate. Each click is checked locally.
Use known app navigation labels or observed labels; a missing/ambiguous target stops the program.
Do not run a chain whose next action needs interpretation of the preceding result.
An unmet condition returns needs_replan and a fresh page. Re-plan from that page.
A failed mutation stops the task; never replay it. Read the returned page before reporting results.
'''

def execute(phone, params, progress=lambda **kw:None):
    program = Program.model_validate(params) # Validate the entire plan before touching a phone.
    steps=[]; status='completed'; started=time.monotonic()
    for index, step in enumerate(program.steps):
        if time.monotonic()-started > 45:
            status='needs_replan'; break
        t=time.monotonic()
        progress(stage='device', current_action=step.action, program_step=index+1, program_total=len(program.steps))
        if step.action in ('click_target','wait_target'):
            deadline=t+step.timeout_ms/1000
            target=None
            while True:
                found=phone.execute({'action':'find_elements','query':step.query})
                if found['count']==1:
                    candidate=found['elements'][0]
                    state=phone.execute({'action':'element_state',**candidate})
                    if state.get('displayed') is True and state.get('enabled') is True:
                        target=candidate;break
                if found['count']>1 or time.monotonic()>=deadline:break
                time.sleep(.15)
            if target is None:
                steps.append({'action':step.action,'ok':False,'reason':'Target missing, ambiguous or not interactable','seconds':round(time.monotonic()-t,3)})
                status='needs_replan';break
            if step.action=='click_target':
                phone.execute({'action':'element_click',**target})
        elif step.action=='read_page':
            pass # A fresh page is always returned below.
        else:
            phone.execute({'action':step.action,**({'bundle_id':step.bundle_id} if step.bundle_id else {})})
        steps.append({'action':step.action,'ok':True,'seconds':round(time.monotonic()-t,3)})
    return {'status':status,'steps':steps,'page':phone.execute({'action':'source_fast'})}
