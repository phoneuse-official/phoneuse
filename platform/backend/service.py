import base64
from contextlib import contextmanager
import hashlib
import json
import re
import os
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from urllib.parse import quote

from .config import setting
from .targeting import Target, selectors, predicate, INPUT_TYPES
from .inventory import inventory as device_cache
from .native_capture import binding_for
from .usb import DeviceError, device_info, list_usb, wda_request

STATE = Path(setting('STATE_DIR') or Path(__file__).resolve().parents[1] / '.state')
STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
DB = STATE / 'platform.sqlite3'


@contextmanager
def database():
    db = sqlite3.connect(DB, timeout=10)
    try:
        db.row_factory = sqlite3.Row
        # SQLite's own context manager commits/rolls back but does not close.
        with db:
            yield db
    finally:
        db.close()


def initialize():
    with database() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS credentials (hash TEXT PRIMARY KEY, name TEXT, devices TEXT);
        CREATE TABLE IF NOT EXISTS leases (device TEXT PRIMARY KEY, owner TEXT, expires REAL);
        CREATE TABLE IF NOT EXISTS device_groups (owner TEXT, name TEXT, devices TEXT, PRIMARY KEY(owner,name));
        CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, time REAL, owner TEXT,
            device TEXT, action TEXT, success INTEGER, error TEXT);
        ''')
    with database() as db:
        if 'expires' not in {r[1] for r in db.execute('PRAGMA table_info(credentials)')}:
            db.execute('ALTER TABLE credentials ADD COLUMN expires REAL')
        db.execute('CREATE TABLE IF NOT EXISTS viewer_blocks(owner TEXT,device TEXT,PRIMARY KEY(owner,device))')
    token_file = STATE / 'admin-token'
    if not token_file.exists():
        token = secrets.token_urlsafe(32)
        fd = os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as f:
            f.write(token)
        add_key(token, 'Local administrator', ['*'])


def add_key(token, name, devices, expires=None):
    digest = hashlib.sha256(token.encode()).hexdigest()
    with database() as db:
        db.execute('INSERT INTO credentials(hash,name,devices,expires) VALUES (?,?,?,?)', (digest, name, json.dumps(devices),expires))


def authenticate(token):
    if not token:
        return None
    digest = hashlib.sha256(token.encode()).hexdigest()
    with database() as db:
        row = db.execute('SELECT * FROM credentials WHERE hash=?', (digest,)).fetchone()
    return dict(row, devices=json.loads(row['devices'])) if row and (row['expires'] is None or row['expires']>time.time()) else None


def allowed(owner, device):
    return '*' in owner['devices'] or device in owner['devices']


class LeaseError(DeviceError):
    pass


class Controller:
    def __init__(self):
        self.locks = {}
        self.guard = threading.Lock()
        self.sessions = {}
        self.stream_profiles = {}
        self.reservations = {}
        self.device_provider = device_cache.snapshot

    def lock(self, device):
        with self.guard:
            return self.locks.setdefault(device, threading.RLock())

    def inventory(self, owner):
        items=[]
        with database() as db:
            leases={r['device']:r for r in db.execute('SELECT * FROM leases WHERE expires>?',(time.time(),))}
        for info in self.device_provider():
            if not allowed(owner,info['id']):continue
            info=dict(info);lease=leases.get(info['id'])
            info['lease']={'mine':lease['owner']==owner['hash'],'expires':lease['expires']} if lease else None
            info['task_id']=self.reservations.get(info['id'])
            items.append(info)
        return items

    def expiry(self, owner, seconds):
        expires=min(time.time()+seconds,owner.get('expires') or float('inf'))
        if expires<=time.time():raise PermissionError('This API key has expired')
        return expires

    def view(self, owner, device):
        if not allowed(owner,device):raise PermissionError('This API key cannot access this phone')
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM viewer_blocks WHERE owner=? AND device=?',(owner['hash'],device)).fetchone():
                raise LeaseError('Screen access was released. Click Reconnect screen to resume')
            current=db.execute('SELECT * FROM leases WHERE device=?',(device,)).fetchone()
            if current and current['expires']>time.time() and current['owner']!=owner['hash']:
                raise LeaseError('Another user is using this phone')
            if not current or current['expires']<=time.time():
                if not any(d['id']==device for d in self.device_provider()):raise DeviceError('Waiting for device discovery')
            expires=self.expiry(owner,900)
            db.execute('INSERT OR REPLACE INTO leases VALUES (?,?,?)',(device,owner['hash'],expires))
        return {'device':device,'expires':expires}

    def renew_view(self, owner, device):
        if not allowed(owner,device):raise PermissionError('This API key cannot access this phone')
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM leases WHERE device=?',(device,)).fetchone()
            if not row or row['owner']!=owner['hash'] or row['expires']<=time.time():raise LeaseError('Phone access has ended')
            expires=self.expiry(owner,900)
            db.execute('UPDATE leases SET expires=? WHERE device=? AND owner=?',(expires,device,owner['hash']))
        return {'expires':expires}

    def acquire(self, owner, device, seconds=300):
        if not allowed(owner, device):
            raise PermissionError('This API key cannot access this phone')
        if not any(d['SerialNumber'] == device for d in list_usb()):
            raise DeviceError('The phone is offline')
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT * FROM leases WHERE device=?', (device,)).fetchone()
            if current and current['expires'] > time.time() and current['owner'] != owner['hash']:
                raise LeaseError('Another user is using this phone')
            expires = self.expiry(owner,seconds)
            db.execute('DELETE FROM viewer_blocks WHERE owner=? AND device=?',(owner['hash'],device))
            db.execute('INSERT OR REPLACE INTO leases VALUES (?,?,?)', (device, owner['hash'], expires))
        return {'device': device, 'expires': expires}

    def release(self, owner, device, block_view=True):
        with database() as db:
            db.execute('DELETE FROM leases WHERE device=? AND owner=?', (device, owner['hash']))
            if block_view:db.execute('INSERT OR IGNORE INTO viewer_blocks VALUES (?,?)',(owner['hash'],device))
        return {'released': True}

    def check_lease(self, owner, device):
        self.expiry(owner,1)
        if not allowed(owner, device):
            raise PermissionError('This API key cannot access this phone')
        with database() as db:
            lease = db.execute('SELECT * FROM leases WHERE device=?', (device,)).fetchone()
        if not lease or lease['owner'] != owner['hash'] or lease['expires'] <= time.time():
            raise LeaseError('Acquire or renew phone access first')

    def session(self, device):
        if device not in self.sessions:
            result = wda_request(device, 'POST', '/session', {'capabilities': {'alwaysMatch': {}}})
            sid = result.get('sessionId') or result.get('value', {}).get('sessionId')
            if not sid:
                raise DeviceError('WDA did not return a session ID')
            self.sessions[device] = sid
        return '/session/' + quote(self.sessions[device], safe='')

    def reserve(self, device, job):
        with self.guard:
            if device in self.reservations:
                raise LeaseError('The phone is running a task')
            self.reservations[device] = job

    def unreserve(self, device, job):
        with self.guard:
            if self.reservations.get(device) == job:
                self.reservations.pop(device, None)

    def check_reservation(self, device, job=None):
        with self.guard:
            if device in self.reservations and self.reservations[device] != job:
                raise LeaseError('The phone is running a task. Stop the task before controlling it manually')

    def perform(self, owner, device, action, params, job=None):
        # Screenshots and state reads stay available during automation.
        reads = ('status', 'screenshot', 'source', 'window_size', 'active_app', 'battery', 'orientation', 'locked', 'source_fast', 'find_elements', 'element_state', 'element_input_state', 'active_element')
        if action not in reads:
            self.check_reservation(device, job)
        with self.lock(device):
            if action not in reads:
                self.check_reservation(device, job)
            self.check_lease(owner, device)
            success, error = False, None
            try:
                result = self._perform(device, action, params)
                success = True
                return result
            except Exception as exc:
                # A failed mutation is never replayed automatically.
                # A stale element invalidates only that handle, not the WDA session.
                # Recreating a healthy session loses task snapshot settings.
                if not (isinstance(exc, DeviceError) and str(exc).lower() == 'wda: stale element reference'):
                    self.sessions.pop(device, None)
                error = str(exc)[:200]
                raise
            finally:
                with database() as db:
                    db.execute('INSERT INTO audit(time,owner,device,action,success,error) VALUES (?,?,?,?,?,?)',
                               (time.time(), owner['hash'], device, action, int(success), error))

    def _perform(self, device, action, p):
        if action == 'status':
            return wda_request(device, 'GET', '/status').get('value')
        if action == 'home':
            return wda_request(device, 'POST', '/wda/homescreen', {}).get('value')
        if action in ('lock', 'unlock', 'locked'):
            return wda_request(device, 'GET' if action == 'locked' else 'POST', '/wda/' + action,
                               None if action == 'locked' else {}).get('value')
        if action in ('clipboard_get', 'clipboard_set'):
            body = {'contentType': 'plaintext'}
            if action == 'clipboard_set':
                body['content'] = base64.b64encode(p['text'].encode('utf-8')).decode('ascii')
            value = wda_request(device, 'POST', '/wda/' + ('getPasteboard' if action == 'clipboard_get' else 'setPasteboard'), body).get('value')
            if action == 'clipboard_get':
                try:
                    return base64.b64decode(value, validate=True).decode('utf-8')
                except (ValueError, TypeError, UnicodeError):
                    raise DeviceError('The phone returned invalid clipboard text')
            return value
        # Element handles are bound to the issuing session; never rebind or replay them.
        if action in ('element_state', 'element_click','element_input_state','element_fill','element_submit_search'):
            if self.sessions.get(device) != p['session_id']:
                raise DeviceError('The element session has expired. Find the element again')
            root = '/session/' + quote(p['session_id'], safe='')
            element = root + '/element/' + quote(p['element_id'], safe='')
            displayed = wda_request(device, 'GET', element + '/displayed').get('value')
            enabled = wda_request(device, 'GET', element + '/enabled').get('value')
            if action in ('element_input_state','element_fill','element_submit_search'):
                def attribute(name):
                    return wda_request(device,'GET',element+'/attribute/'+name).get('value')
                kind=wda_request(device,'GET',element+'/name').get('value')
                # Do not retrieve secure input values, even for the read-only probe.
                if kind not in INPUT_TYPES:
                    return {'eligible':False,'reason':'Target is not a supported editable input'}
                label=' '.join(str(attribute(name) or '') for name in ('name','label'))
                eligible=displayed is True and enabled is True
                value=attribute('value')
                placeholder=attribute('placeholderValue')
                searchable=kind=='XCUIElementTypeSearchField' or bool(re.search(r'search|address|url|website',label,re.I))
                state={'eligible':eligible,'type':kind,'value':value,'searchable':searchable}
                if action=='element_input_state':return state
                if not eligible:return {'status':'needs_replan','reason':'Input is hidden or disabled'}
                if action=='element_fill':
                    if value==p['text'] and value!=placeholder:return {'status':'completed','verified':True,'already_matched':True}
                    # Bind every mutation to this exact handle; never use global keyboard typing.
                    wda_request(device,'POST',element+'/click',{})
                    wda_request(device,'POST',element+'/clear',{})
                    wda_request(device,'POST',element+'/value',{'value':list(p['text'])})
                    verified=attribute('value')==p['text'] and p['text']!=placeholder
                    return {'status':'completed' if verified else 'uncertain','verified':verified,
                            'reason':None if verified else 'Entered text could not be verified; do not retype automatically'}
                if not searchable:return {'status':'needs_replan','reason':'Submission is limited to observed search or address fields'}
                if value!=p['text'] or value==placeholder:return {'status':'needs_replan','reason':'Field value does not match a verified query; nothing submitted'}
                wda_request(device,'POST',element+'/value',{'value':['\n']})
                return {'status':'submitted'}
            if action == 'element_click':
                if displayed is not True or enabled is not True:
                    raise DeviceError('The element is hidden or disabled; nothing was tapped')
                # This is a precheck, not a guarantee against overlays or subsequent UI changes.
                return wda_request(device, 'POST', element + '/click', {}).get('value')
            rect = wda_request(device, 'GET', element + '/rect').get('value')
            return {'session_id': p['session_id'], 'element_id': p['element_id'],
                    'displayed': displayed, 'enabled': enabled, 'rect': rect}
        if action == 'stream_settings' and binding_for(device):
            self.stream_profiles[device]={k:p[k] for k in ('fps','quality','scale')}
            return {'transport':'native-usb',**self.stream_profiles[device]}
        root = self.session(device)
        if action == 'source_fast':
            xml = wda_request(device, 'GET', root + '/source?format=xml&excluded_attributes=visible,accessible').get('value')
            return {'format': 'xml', 'source': xml, 'excluded_attributes': ['visible', 'accessible'],
                    'requires_target_verification': True}
        if action == 'active_element':
            try:value=wda_request(device,'GET',root+'/element/active').get('value')
            except DeviceError as exc:
                if str(exc)=='WDA: no such element':return None
                raise
            if not value:return None
            ident=value.get('element-6066-11e4-a52e-4f735466cecf') or value.get('ELEMENT')
            if not isinstance(ident,str) or not ident:raise DeviceError('Invalid active element handle')
            return {'session_id':self.sessions[device],'element_id':ident,
                'attributes':{k:value[k] for k in ('type','label','displayed','enabled','rect') if k in value}}
        if action == 'find_elements':
            target=Target.model_validate(p['target']) if p.get('target') else Target(label=p['query'])
            search_root=root
            def find(using,value,path):
                result=wda_request(device,'POST',path+'/elements',{'using':using,'value':value}).get('value')
                if not isinstance(result,list):raise DeviceError('The phone returned an invalid element list')
                return result
            def handle(item):
                if not isinstance(item,dict):raise DeviceError('The phone returned an invalid element ID')
                ident=item.get('element-6066-11e4-a52e-4f735466cecf') or item.get('ELEMENT')
                if not isinstance(ident,str) or not ident:raise DeviceError('The phone returned an invalid element ID')
                return ident
            if target.within:
                scopes=find('predicate string',predicate(target.within),root)
                if len(scopes)!=1:
                    return {'elements':[],'count':0,'reason':'container_missing' if not scopes else 'container_ambiguous'}
                search_root=root+'/element/'+quote(handle(scopes[0]),safe='')
            found=[];strategy=None
            for strategy,value in selectors(target):
                found=find(strategy,value,search_root)
                if found:break
            elements=[]
            for item in found:
                candidate={'element_id':handle(item),'session_id':self.sessions[device]}
                # WDA's top-level `name` means element TYPE, not accessibility name.
                # Request attribute/name explicitly; never enrich input values.
                attrs={k:item[k] for k in ('type','label','rect','enabled','displayed') if k in item}
                if 'attribute/name' in item:attrs['name']=item['attribute/name']
                if attrs:candidate['attributes']=attrs
                elements.append(candidate)
            return {'elements':elements,'count':len(elements),'strategy':strategy,
                    'reason':None if elements else 'missing'}
        if action == 'alert_text':
            return wda_request(device, 'GET', root + '/alert/text').get('value')
        if action == 'pinch':
            size = wda_request(device, 'GET', root + '/window/size')['value']
            # Horizontal, simultaneous fingers; endpoints remain inside the viewport.
            scale = p['scale']
            outer = min(p['x'], 1 - p['x'], 0.35) * 0.9
            start_radius = outer / max(1, scale)
            end_radius = start_radius * scale
            fingers = []
            for index, sign in enumerate((-1, 1)):
                y = round(p['y'] * (size['height'] - 1))
                fingers.append({'type': 'pointer', 'id': f'finger{index}', 'parameters': {'pointerType': 'touch'}, 'actions': [
                    {'type': 'pointerMove', 'duration': 0, 'origin': 'viewport', 'x': round((p['x'] + sign * start_radius) * (size['width'] - 1)), 'y': y},
                    {'type': 'pointerDown', 'button': 0},
                    {'type': 'pointerMove', 'duration': p.get('duration_ms', 400), 'origin': 'viewport', 'x': round((p['x'] + sign * end_radius) * (size['width'] - 1)), 'y': y},
                    {'type': 'pointerUp', 'button': 0}]})
            return wda_request(device, 'POST', root + '/actions', {'actions': fingers}).get('value')
        if action == 'stream_settings':
            settings = {'mjpegServerFramerate': p['fps'], 'mjpegServerScreenshotQuality': p['quality'],
                        'mjpegScalingFactor': p['scale']}
            result = wda_request(device, 'POST', root + '/appium/settings', {'settings': settings}).get('value')
            self.stream_profiles[device] = {k:p[k] for k in ('fps','quality','scale')}
            return result
        if action in ('screenshot', 'source', 'window_size', 'active_app', 'battery', 'orientation'):
            paths = {'screenshot': '/screenshot', 'source': '/source', 'window_size': '/window/size',
                     'active_app': '/wda/activeAppInfo', 'battery': '/wda/batteryInfo', 'orientation': '/orientation'}
            return wda_request(device, 'GET', root + paths[action]).get('value')
        if action in ('tap', 'swipe', 'long_press', 'double_tap'):
            size = wda_request(device, 'GET', root + '/window/size')['value']
            def point(x, y):
                return round(p[x] * (size['width'] - 1)), round(p[y] * (size['height'] - 1))
            x, y = point('x', 'y')
            steps = [{'type': 'pointerMove', 'duration': 0, 'origin': 'viewport', 'x': x, 'y': y},
                     {'type': 'pointerDown', 'button': 0}]
            if action == 'swipe':
                x2, y2 = point('x2', 'y2')
                steps.append({'type': 'pointerMove', 'duration': p.get('duration_ms', 400),
                              'origin': 'viewport', 'x': x2, 'y': y2})
            else:
                steps.append({'type': 'pause', 'duration': p.get('duration_ms', 800) if action == 'long_press' else 60})
            steps.append({'type': 'pointerUp', 'button': 0})
            if action == 'double_tap':
                steps.extend([{'type': 'pause', 'duration': 100}, {'type': 'pointerDown', 'button': 0},
                              {'type': 'pause', 'duration': 60}, {'type': 'pointerUp', 'button': 0}])
            return wda_request(device, 'POST', root + '/actions', {'actions': [
                {'type': 'pointer', 'id': 'finger', 'parameters': {'pointerType': 'touch'}, 'actions': steps}]}).get('value')
        routes = {
            'accept_alert': ('/alert/accept', {}),
            'dismiss_alert': ('/alert/dismiss', {}),
            'dismiss_keyboard': ('/wda/keyboard/dismiss', {}),
            'text': ('/wda/keys', {'value': list(p.get('text', ''))}),
            'home': ('/wda/homescreen', {}),
            'button': ('/wda/pressButton', {'name': p.get('name')}),
            'launch_app': ('/wda/apps/launch', {'bundleId': p.get('bundle_id')}),
            'terminate_app': ('/wda/apps/terminate', {'bundleId': p.get('bundle_id')}),
            'open_url': ('/url', {'url': p.get('url')}),
            'set_orientation': ('/orientation', {'orientation': p.get('orientation')}),
        }
        path, body = routes[action]
        return wda_request(device, 'POST', root + path, body).get('value')


initialize()
controller = Controller()
