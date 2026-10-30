"""Rehearsed Calendar → Maps demo. Executes real UI actions, no fabricated completion."""
import base64
import copy
import json
import math
import threading
import time
import uuid
import xml.etree.ElementTree as ET
from urllib.parse import quote
from fastapi import Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from . import service, demo_invitation as invitation
from .codex_api import LocalPhone
from .usb import DeviceError

EVENT={'title':'Design Night','date':'September 19, 2026','start':'19:00','end':'20:00','venue':'Ferry Building','venue_query':'Ferry Building, San Francisco','alert':'1 hour before','timezone':'Device local time'}
PROMPT='Plan a design night at the Ferry Building on Sept 19 at 7pm. Invite Alex.'
PHASES=['Review event details','Prepare calendar event','Save with a one-hour reminder','Find the venue in Maps','Prepare Alex’s invitation poster','Send after your confirmation']
CAL='com.apple.mobilecal'; MAP='com.apple.mobilesafari'; GOOGLE_MAPS='com.google.Maps'


def calendar_suggestion_point(root, *, natural_language_title, event_title):
    width = float(root.get('width', '0'))
    height = float(root.get('height', '0'))
    title_fields = [n for n in root.iter()
                    if n.get('name') == 'title-field'
                    and n.get('type', '').endswith('TextField')
                    and n.get('value') == natural_language_title]
    parents = {child: parent for parent in root.iter() for child in parent}
    cells = []
    for node in root.iter():
        if not (node.get('type', '').endswith('StaticText')
                and event_title in (node.get('name'), node.get('label'))):
            continue
        cell = node
        while cell is not None and not cell.get('type', '').endswith('Cell'):
            cell = parents.get(cell)
        if cell is not None and cell not in cells:
            cells.append(cell)
    valid = [cell for cell in cells
             if cell.get('enabled') == 'true'
             and float(cell.get('width', '0')) > 0
             and float(cell.get('height', '0')) > 0]
    if len(title_fields) != 1 or len(valid) != 1 or width <= 0 or height <= 0:
        raise RuntimeError('The Calendar suggestion is not uniquely visible.')
    cell = valid[0]
    x = (float(cell.get('x', '0')) + float(cell.get('width', '0')) / 2) / width
    y = (float(cell.get('y', '0')) + float(cell.get('height', '0')) / 2) / height
    if not 0 < x < 1 or not 0 < y < 1:
        raise RuntimeError('The Calendar suggestion is not uniquely visible.')
    return x, y


def normalized_calendar_text(value):
    return ' '.join((value or '').replace('\u00a0', ' ').replace('\u202f', ' ').split())


def finite_float(value):
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def calendar_editor_has_expected_time(root):
    starts = [normalized_calendar_text(n.get('label')) for n in root.iter()
              if n.get('name') == 'start-date-picker-cell']
    ends = [normalized_calendar_text(n.get('label')) for n in root.iter()
            if n.get('name') == 'end-date-picker-cell']
    return (starts, ends) in (
        (['Starts, 7:00 PM, Sep 19, 2026'], ['Ends, 8:00 PM, Sep 19, 2026']),
        (['Starts, 19:00, Sep 19, 2026'], ['Ends, 20:00, Sep 19, 2026']),
    )


def calendar_details_match(root):
    titles = [n for n in root.iter()
              if n.get('name') == 'event-details-title-text'
              and EVENT['title'] in (n.get('label'), n.get('value'))]
    venues = [n for n in root.iter()
              if n.get('type', '').endswith('TextView')
              and (n.get('value') or '').splitlines()[:1] == [EVENT['venue']]]
    dates = [n for n in root.iter()
             if 'Saturday, Sep 19, 2026' in (n.get('name'), n.get('label'), n.get('value'))]
    reminders = [n for n in root.iter()
                 if n.get('name') == 'alert-cell' and n.get('value') == EVENT['alert']]
    accepted_times = {', from 7:00 PM to 8:00 PM', ', from 19:00 to 20:00'}
    times = [n for n in root.iter()
             if n.get('name') == 'event-shown:' + EVENT['title']
             and normalized_calendar_text(n.get('label')).startswith(EVENT['title'] + ', ')
             and any(fragment in normalized_calendar_text(n.get('label'))
                     for fragment in accepted_times)]
    return bool(venues) and all(len(items) == 1 for items in (titles, dates, reminders, times))


def maps_page_matches(bundle_id, root):
    raw = ET.tostring(root, encoding='unicode')
    if bundle_id == MAP:
        return all(value in raw for value in (EVENT['venue'], 'Directions', 'Historical landmark', 'google.com'))
    if bundle_id != GOOGLE_MAPS:
        return False
    width = finite_float(root.get('width'))
    height = finite_float(root.get('height'))
    if width is None or height is None or width <= 0 or height <= 0:
        return False
    queries = [n for n in root.iter()
               if n.get('name') == 'SearchHeaderSearchTxtView'
               and n.get('value') == EVENT['venue_query'].replace(',', '')
               and n.get('enabled') == 'true']
    titles = [n for n in root.iter()
              if n.get('type', '').endswith('StaticText')
              and EVENT['venue'] in (n.get('name'), n.get('label'))
              and n.get('enabled') == 'true']
    landmarks = [n for n in root.iter()
                 if normalized_calendar_text(n.get('name')).startswith('Historical landmark')]
    directions = []
    for node in root.iter():
        if not (node.get('type', '').endswith('Button')
                and node.get('name') == 'Directions'
                and node.get('enabled') == 'true'):
            continue
        x, y, node_width, node_height = (finite_float(node.get(key))
                                         for key in ('x', 'y', 'width', 'height'))
        if (None not in (x, y, node_width, node_height)
                and 0 <= x < width and 0 <= y < height
                and node_width > 0 and node_height > 0):
            directions.append(node)
    if not all(len(items) == 1 for items in (queries, titles, landmarks, directions)):
        return False
    parents = {child: parent for parent in root.iter() for child in parent}
    chains = []
    for node in (titles[0], landmarks[0], directions[0]):
        chain = []
        while node is not None:
            chain.append(node)
            node = parents.get(node)
        chains.append(chain)
    common = [node for node in chains[0] if all(node in chain for chain in chains[1:])]
    if not common:
        return False
    card = common[0]
    card_x, card_y, card_width, card_height = (finite_float(card.get(key))
                                               for key in ('x', 'y', 'width', 'height'))
    if None in (card_x, card_y, card_width, card_height):
        return False
    if not (card.get('type', '').endswith('Other')
            and 0 <= card_x <= width * .1
            and height * .35 <= card_y < height
            and card_width >= width * .9
            and card_x + card_width >= width * .9
            and card_y + card_height >= height):
        return False
    node = queries[0]
    while node is not None:
        if node is card:
            return False
        node = parents.get(node)
    direction = directions[0]
    direction_x = finite_float(direction.get('x')) + finite_float(direction.get('width')) / 2
    direction_y = finite_float(direction.get('y')) + finite_float(direction.get('height')) / 2
    if not (0 < direction_x < width and 0 < direction_y < height
            and card_x <= direction_x <= card_x + card_width
            and card_y <= direction_y <= card_y + card_height):
        return False
    # A generic page wrapper is not proof that all signals describe one place.
    # At most one intervening result/action Cell may contain these three nodes.
    intervening_cells = set()
    for node in (titles[0], landmarks[0], directions[0]):
        while node is not None and node is not card:
            if node.get('type', '').endswith('Cell'):
                intervening_cells.add(node)
                break
            node = parents.get(node)
    return len(intervening_cells) <= 1


class Request(BaseModel):
    model_config=ConfigDict(extra='forbid')
    device_id:str=Field(pattern=r'^[A-Za-z0-9_-]{1,128}$')
    prompt:str=Field(min_length=1,max_length=1000)
    resume_draft:bool=False

class Confirmation(BaseModel):
    model_config=ConfigDict(extra='forbid')
    message:str=Field(min_length=1,max_length=50)

class DemoPhone(LocalPhone):
    def __init__(self,*args):
        super().__init__(*args);self.deadline=time.monotonic()+180
    def act(self,action,**params):
        self.check()
        if time.monotonic()>self.deadline:raise RuntimeError('Demo timed out. Inspect the phone before another take.')
        if action not in {'launch_app','source_fast','source','tap','text','swipe','open_url','screenshot','active_app','find_elements','element_state','element_click','long_press'}:raise ValueError('Unsupported demo action')
        started=time.monotonic()
        self.progress(action=action)
        try:return service.controller.perform(self.owner,self.device,action,params,job=self.task_id)
        finally:self.progress(action=action,seconds=round(time.monotonic()-started,3))
    def tree(self):
        return ET.fromstring(self.act('source_fast')['source'])
    def find(self,name,kind=None,timeout=6):
        end=time.monotonic()+timeout
        while True:
            root=self.tree();h=float(root.get('height','0'));w=float(root.get('width','0'))
            nodes=[n for n in root.iter() if n.get('enabled')=='true' and name in (n.get('name'),n.get('label')) and (kind is None or n.get('type','').endswith(kind)) and 0<float(n.get('height',0)) and 0<=float(n.get('y',-1))<h-25 and 0<=float(n.get('x',-1))<w]
            if nodes:return root,nodes[-1]
            if time.monotonic()>=end:raise RuntimeError('Expected screen item not found: '+name)
            self.cancel.wait(.2)
    def has(self,name):
        try:self.find(name,timeout=0);return True
        except RuntimeError:return False
    def click(self,name,kind=None,timeout=6):
        # Menu animations may invalidate even a read-only /elements request.
        # Refresh the whole selection, never replay a failed mutation.
        for attempt in range(3):
            self.check()
            try:
                root,node=self.find(name,kind,timeout)
                found=self.act('find_elements',query=name)['elements']
                candidates=[]
                for element in found:
                    state=self.act('element_state',**element)
                    rect=state.get('rect',{})
                    if state.get('displayed') and state.get('enabled') and abs(float(rect.get('y',-999))-float(node.get('y',0)))<3:candidates.append(element)
                if len(candidates)!=1:raise RuntimeError('Screen target is not uniquely visible: '+name)
                break
            except DeviceError as exc:
                if 'stale element reference' not in str(exc).lower() or attempt==2:raise
                self.cancel.wait(.3)
        self.act('element_click',**candidates[0])
        self.cancel.wait(.35)
    def require(self,*values):
        end=time.monotonic()+6
        while True:
            raw=ET.tostring(self.tree(),encoding='unicode')
            if all(v in raw for v in values):return
            if time.monotonic()>end:raise RuntimeError('The phone did not confirm the expected event details.')
            self.cancel.wait(.2)
    def require_editor_time(self):
        end=time.monotonic()+6
        while True:
            if calendar_editor_has_expected_time(self.tree()):return
            if time.monotonic()>end:raise RuntimeError('The phone did not confirm the expected event time.')
            self.cancel.wait(.2)
    def calendar_root(self):
        self.act('launch_app',bundle_id=CAL);self.cancel.wait(.45)
        for _ in range(6):
            if self.has('add-button'):raise RuntimeError('An event editor is open. Close it before starting the demo.')
            if self.has('event-details-title-text'):self.click('BackButton','Button');continue
            if self.has('Close'):self.click('Close','Button');continue
            if self.has('searchbar-button'):return
            if self.has('Cancel'):self.click('Cancel','Button')
            elif self.has('BackButton'):self.click('BackButton','Button')
            elif self.has('Back'):self.click('Back','Button')
            else:raise RuntimeError('Open the Calendar main screen before starting the demo.')
        raise RuntimeError('Calendar navigation did not reach the main screen.')
    def search_event(self):
        self.calendar_root();self.click('searchbar-button','Button')
        self.act('text',text=EVENT['title']);self.cancel.wait(.5)
        try:self.click(EVENT['title'],'StaticText',timeout=3)
        except RuntimeError:
            self.require('No Results')
            self.click('Close','Button')
            return False
        self.require(EVENT['title'],EVENT['venue'])
        return True
    def verify_event(self):
        self.find('event-details-title-text','StaticText')
        end=time.monotonic()+6
        while True:
            if calendar_details_match(self.tree()):return
            if time.monotonic()>end:raise RuntimeError('The phone did not confirm the expected saved event.')
            self.cancel.wait(.2)
    def create(self,phase):
        self.click('add-plus-button','Button');self.find('title-field')
        natural_title='Design Night on September 19, 2026 from 7 PM to 8 PM'
        self.act('text',text=natural_title)
        x,y=calendar_suggestion_point(self.tree(),natural_language_title=natural_title,event_title=EVENT['title'])
        self.act('tap',x=x,y=y);self.cancel.wait(.35)
        self.require_editor_time()
        self.click('Location or Video Call','StaticText');self.find('location-video-call-search-field')
        self.act('text',text=EVENT['venue_query'])
        # Calendar permits a literal location when its regional search has no POI.
        # Maps is independently checked later for the actual venue.
        try:self.find(EVENT['venue'],'StaticText',timeout=5);target=EVENT['venue']
        except RuntimeError:
            target='“'+EVENT['venue_query']+'”'
            self.find(target,'StaticText',timeout=5)
        self.click(target,'StaticText')
        self.find('title-field')
        phase(2)
        self.finish_draft()
    def finish_draft(self):
        _,title=self.find('title-field','TextField')
        if title.get('value')!=EVENT['title']:raise RuntimeError('This draft is not the prepared demo event.')
        self.require('Design Night',EVENT['venue']);self.require_editor_time()
        if not self.has('At time of event'):self.click('Alert','StaticText')
        self.click('1 hour before','Button')
        self.require('1 hour before',EVENT['venue']);self.require_editor_time()
        self.click('add-button','Button');self.cancel.wait(.6)
        if not self.search_event():raise RuntimeError('Saved event was not found. Do not repeat until the calendar is checked.')
        self.verify_event()
    def maps(self):
        self.act('open_url',url='https://www.google.com/maps/search/?api=1&query='+quote(EVENT['venue_query'].replace(',',''))+'&hl=en')
        self.cancel.wait(.7)
        # No location access is necessary for this named-venue search.
        for name in ('Go back to web',):
            if self.has(name):self.click(name,'Button')
        selected_result=False
        end=time.monotonic()+30
        while time.monotonic()<end:
            app=self.act('active_app')
            root=self.tree();raw=ET.tostring(root,encoding='unicode')
            if maps_page_matches(app.get('bundleId'),root):return
            if 'Go back to web' in raw:
                self.click('Go back to web','Button');continue
            if app.get('bundleId')==MAP and 'Get directions to Ferry Building' in raw and not selected_result:
                matches=[n for n in root.iter() if n.get('type','').endswith('Button') and n.get('name')==EVENT['venue'] and any(c.get('name')=='Historical landmark' for c in n.iter())]
                if len(matches)==1:
                    n=matches[0];x=(float(n.get('x'))+float(n.get('width'))/2)/float(root.get('width'));y=(float(n.get('y'))+float(n.get('height'))/2)/float(root.get('height'))
                    if 0<x<1 and 0<y<1:
                        self.act('tap',x=x,y=y);selected_result=True;self.cancel.wait(.5);continue
            self.cancel.wait(.3)
        raise RuntimeError('Maps has not confirmed the venue. Calendar changes may already be saved.')

class Manager:
    def __init__(self):self.lock=threading.RLock();self.tasks={};self.active=None
    def public(self,e):return copy.deepcopy(e['record'])
    def start(self,owner,body):
        if not service.allowed(owner,body.device_id):raise PermissionError('Device access denied')
        if ' '.join(body.prompt.split()).rstrip('.').casefold()!=PROMPT.rstrip('.').casefold():raise ValueError('This scripted demo supports the prepared event request. Use the suggested prompt.')
        with self.lock:
            if self.active:raise HTTPException(409,'A demo is already running')
            id=uuid.uuid4().hex
            e={'owner':owner['hash'],'cancel':threading.Event(),'proofs':{},'record':{'id':id,'device_id':body.device_id,'prompt':body.prompt,'status':'running','phase':0,'phases':PHASES,'started':time.time(),'event':EVENT,'mode':'scripted-demo','resume_draft':body.resume_draft}}
            self.tasks[id]=e;self.active=id
            while len(self.tasks)>10:self.tasks.pop(next(iter(self.tasks)))
            t=threading.Thread(target=self.worker,args=(owner,e),daemon=True);e['thread']=t;t.start();return self.public(e)
    def worker(self,owner,e):
        r=e['record']
        def progress(**kw):
            with self.lock:
                r['current_action']=kw['action']
                if 'seconds' in kw:r.setdefault('trace',[]).append(kw)
        p=DemoPhone(owner,r['device_id'],r['id'],e['cancel'],progress)
        def phase(n):
            p.check()
            with self.lock:r['phase']=n
        def proof(name):
            data=base64.b64decode(p.act('screenshot'),validate=True)
            with self.lock:e['proofs'][name]=data;r[name+'_proof']=True
        try:
            p.acquire();phase(0);p.cancel.wait(.6);phase(1)
            existed=False if r.get('resume_draft') else p.search_event()
            if existed:
                with self.lock:r['phases']=['Review event details','Open saved event','Verify the existing reminder',*PHASES[3:]]
                phase(2);p.verify_event()
            elif r.get('resume_draft'):phase(2);p.finish_draft()
            else:p.create(phase)
            with self.lock:r['calendar_verified']=True;r['reused_event']=existed
            proof('calendar');phase(3);p.maps()
            with self.lock:r['maps_verified']=True
            proof('map');phase(4)
            preview,contact_name,address,png,sample=invitation.prepare(p)
            with self.lock:
                e['contact_name']=contact_name;e['address']=address;e['sample']=sample;e['proofs']['invitation']=png
                r['invitation']=preview;r['invitation_proof']=True;r['phase']=5
            with self.lock:
                r['status']='awaiting_confirmation'
                r['answer']='Is it good?'
        except Exception as exc:
            with self.lock:r['status']='cancelled' if e['cancel'].is_set() else 'blocked';r['error']=str(exc)[:250] if not any('\u3400'<=ch<='\u9fff' for ch in str(exc)) else 'Phone connection needs attention. Check the device workspace and try again.'
        finally:
            try:p.close()
            except Exception:
                with self.lock:r['cleanup_error']='Device cleanup needs attention.'
            with self.lock:
                r['finished']=time.time()
                if r.get('status')!='awaiting_confirmation':self.active=None
    def confirm(self,owner,id,message):
        with self.lock:
            e=self.entry(owner,id);r=e['record']
            if ' '.join(message.split()).rstrip('.!').casefold() != 'yes send it':raise ValueError('Review the invitation, then enter “yes send it”')
            if r.get('send_attempted') or r.get('status')=='completed':return self.public(e)
            if r.get('status')!='awaiting_confirmation' or e['cancel'].is_set():raise HTTPException(409,'This invitation is not awaiting confirmation.')
            r['status']='running';r['confirmation']=message.strip();r.pop('finished',None);r.pop('answer',None)
            self.active=id
            t=threading.Thread(target=self.send_worker,args=(owner,e),daemon=True);e['thread']=t;t.start()
            return self.public(e)
    def send_worker(self,owner,e):
        r=e['record'];p=DemoPhone(owner,r['device_id'],r['id'],e['cancel'],lambda **kw:None)
        def attempted():
            p.check()
            with self.lock:r['send_attempted']=True
        try:
            p.acquire()
            invitation.send(p,e['contact_name'],e['address'],e['sample'],attempted)
            png=base64.b64decode(p.act('screenshot'),validate=True)
            with self.lock:
                e['proofs']['message']=png;r['message_proof']=True;r['status']='completed'
                r['answer']='Done.'
        except Exception as exc:
            with self.lock:
                r['status']='delivery_unverified' if r.get('send_attempted') else 'blocked'
                r['error']=str(exc)[:250]
        finally:
            try:p.close()
            except Exception:r['cleanup_error']='Device cleanup needs attention.'
            with self.lock:r['finished']=time.time();self.active=None
    def entry(self,owner,id):
        e=self.tasks.get(id)
        if not e or e['owner']!=owner['hash'] or not service.allowed(owner,e['record']['device_id']):raise HTTPException(404,'Demo not found')
        return e
    def stop(self):
        for e in list(self.tasks.values()):e['cancel'].set()
        for e in list(self.tasks.values()):e['thread'].join(timeout=3)

manager=Manager()
def register_routes(app,owner):
    @app.get('/api/demo')
    def info(user=Depends(owner)):
        with manager.lock:return {'event':EVENT,'prompt':PROMPT,'phases':PHASES,'tasks':[manager.public(e) for e in manager.tasks.values() if e['owner']==user['hash'] and service.allowed(user,e['record']['device_id'])]}
    @app.post('/api/demo/tasks',status_code=202)
    def start(body:Request,user=Depends(owner)):return manager.start(user,body)
    @app.post('/api/demo/tasks/{id}/cancel')
    def cancel(id:str,user=Depends(owner)):
        with manager.lock:
            e=manager.entry(user,id);e['cancel'].set()
            if e['record']['status']=='awaiting_confirmation':
                e['record']['status']='cancelled';manager.active=None
            return manager.public(e)
    @app.post('/api/demo/tasks/{id}/confirm',status_code=202)
    def confirm(id:str,body:Confirmation,user=Depends(owner)):
        return manager.confirm(user,id,body.message)
    @app.get('/api/demo/invitation')
    def asset(user=Depends(owner)):
        return Response(invitation.ASSET.read_bytes(),media_type='image/png',headers={'Cache-Control':'no-store'})
    @app.get('/api/demo/tasks/{id}/proof/{name}')
    def proof(id:str,name:str,user=Depends(owner)):
        with manager.lock:
            e=manager.entry(user,id);data=e['proofs'].get(name)
            if not data:raise HTTPException(404,'Proof not available')
            return Response(data,media_type='image/png' if data.startswith(b'\x89PNG') else 'image/jpeg',headers={'Cache-Control':'no-store'})
