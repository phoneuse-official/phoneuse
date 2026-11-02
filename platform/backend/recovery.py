"""Bounded WDA supervision for explicitly enrolled USB devices."""
import json
import os
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .service import STATE, allowed, controller, database
from .usb import DeviceError, list_usb, wda_request

PROJECT = Path(__file__).resolve().parents[1]


def initialize():
    with database() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS recovery_devices(device TEXT PRIMARY KEY,enabled INTEGER,updated REAL);
        CREATE TABLE IF NOT EXISTS recovery_events(id INTEGER PRIMARY KEY,time REAL,device TEXT,state TEXT,detail TEXT);
        ''')


def configure(user, device, enabled):
    if '*' not in user['devices']:
        raise PermissionError('Only the local administrator can change automatic recovery')
    if not device or len(device)>100 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-' for c in device):
        raise ValueError('Invalid device identifier')
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        if not db.execute('SELECT 1 FROM recovery_devices WHERE device=?',(device,)).fetchone() and db.execute('SELECT COUNT(*) FROM recovery_devices').fetchone()[0]>=20:
            raise ValueError('One Mac can manage at most 20 phones')
        db.execute('INSERT OR REPLACE INTO recovery_devices VALUES (?,?,?)',(device,int(enabled),time.time()))
    return {'device':device,'enabled':enabled}


class Supervisor:
    def __init__(self):
        self.stop_event=threading.Event()
        self.thread=None
        self.guard=threading.RLock()
        self.states={}
        self.children={}
        self.started=time.time()

    def state(self, device, phase, detail, **extra):
        with self.guard:
            old=self.states.get(device,{})
            changed=old.get('phase')!=phase or old.get('detail')!=detail
            self.states[device]={**old,**extra,'phase':phase,'detail':detail,'checked_at':time.time()}
        if changed:
            with database() as db:
                db.execute('INSERT INTO recovery_events(time,device,state,detail) VALUES (?,?,?,?)',(time.time(),device,phase,detail))
                db.execute('DELETE FROM recovery_events WHERE id NOT IN (SELECT id FROM recovery_events ORDER BY id DESC LIMIT 500)')

    def snapshot(self, user):
        with database() as db:
            settings=db.execute('SELECT * FROM recovery_devices').fetchall()
        with self.guard:
            return [{'device':r['device'],'enabled':bool(r['enabled']),**self.states.get(r['device'],{'phase':'pending' if r['enabled'] else 'disabled','detail':'Waiting for a health check'})} for r in settings if allowed(user,r['device'])]

    def terminate(self, device):
        with self.guard:
            process=self.children.pop(device,None)
        if process and process.poll() is None:
            try:
                os.killpg(process.pid,signal.SIGTERM)
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL)
                process.wait(timeout=2)
            except ProcessLookupError:
                pass

    def spawn(self, device):
        # start-wda.py holds a per-device flock across exec, preventing duplicate launchers.
        logs=STATE/'wda-logs';logs.mkdir(exist_ok=True,mode=0o700)
        path=logs/(device+'.log')
        if path.exists():
            previous=logs/(device+'.previous.log')
            path.replace(previous)
        process=subprocess.Popen([sys.executable,str(PROJECT/'start-wda.py'),device,'--parent-pid',str(os.getpid())],cwd=PROJECT,
            stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,start_new_session=True)
        def drain():
            try:
                with process.stdout as source:
                    size=0
                    log=path.open('wb');path.chmod(0o600)
                    try:
                        while chunk:=source.read1(8192):
                            if size+len(chunk)>2*1024*1024:
                                log.close();path.replace(logs/(device+'.previous.log'))
                                log=path.open('wb');path.chmod(0o600);size=0
                            log.write(chunk);log.flush();size+=len(chunk)
                    finally:log.close()
            except OSError:
                pass
        threading.Thread(target=drain,daemon=True,name='wda-log-'+device[-8:]).start()
        with self.guard:
            self.children[device]=process
        return process

    def tick_device(self, config, online):
        if self.stop_event.is_set():return
        device=config['device'];now=time.time()
        with self.guard:
            state=dict(self.states.get(device,{}));process=self.children.get(device)
        if not config['enabled']:
            self.state(device,'disabled','Automatic recovery is off; a running WDA is not stopped',generation=config['updated'])
            return
        if state.get('generation')!=config['updated']:
            state={'generation':config['updated'],'attempts':0,'failures':0,'next_retry':0}
            with self.guard:self.states[device]=state
        if device not in online:
            self.terminate(device)
            if controller.lock(device).acquire(blocking=False):
                try:controller.sessions.pop(device,None)
                finally:controller.lock(device).release()
            self.state(device,'offline','Waiting for USB to reconnect',failures=0,healthy_since=0)
            return
        try:
            healthy=wda_request(device,'GET','/status',timeout=3).get('value',{}).get('ready') is True
        except (DeviceError,OSError):
            healthy=False
        if healthy:
            since=state.get('healthy_since') or now
            self.state(device,'ready','WDA is healthy; automatic recovery is on',failures=0,healthy_since=since,
                       attempts=0 if now-since>=30 else state.get('attempts',0),next_retry=0)
            return
        failures=state.get('failures',0)+1
        with self.guard:
            self.states[device].update(failures=failures,healthy_since=0)
        if device in controller.reservations:
            self.state(device,'waiting_idle','A task is still running; WDA will be recovered after it ends')
            return
        if process and process.poll() is None and now-state.get('launched_at',0)<120:
            self.state(device,'starting','WDA is starting; keep the iPhone unlocked')
            return
        if failures<3:
            self.state(device,'probing','Rechecking the WDA connection before restarting')
            return
        attempts=state.get('attempts',0)
        if attempts>=5:
            cooldown=state.get('cooldown_until',0)
            if not cooldown or now<cooldown:
                self.terminate(device)
                cooldown=cooldown or now+300
                self.state(device,'needs_attention','Recovery has not finished and will retry after a cooldown. Check that the iPhone trusts this Mac, Developer Mode is on and WDA is installed',cooldown_until=cooldown,next_retry=cooldown)
                return
            attempts=0
            with self.guard:self.states[device].update(attempts=0,next_retry=0,cooldown_until=0)
            state['next_retry']=0
        if now<state.get('next_retry',0):
            self.state(device,'retrying','Waiting for the next recovery attempt')
            return
        lock=controller.lock(device)
        if not lock.acquire(blocking=False):
            self.state(device,'waiting_idle','The iPhone is busy; recovery will run later')
            return
        reserved=False
        try:
            # Reservation makes task startup and recovery mutually exclusive.
            controller.reserve(device,'recovery');reserved=True
            self.terminate(device)
            controller.sessions.pop(device,None)
            if self.stop_event.is_set():return
            self.spawn(device)
            attempts+=1
            self.state(device,'starting','WDA recovery started; keep the iPhone unlocked',attempts=attempts,
                       launched_at=now,next_retry=now+min(300,10*2**(attempts-1)))
        except DeviceError:
            self.state(device,'waiting_idle','WDA will be recovered after the task ends')
        except OSError:
            self.state(device,'retrying','Could not start the local WDA launcher; retrying soon',attempts=attempts+1,next_retry=now+30)
        finally:
            if reserved:controller.unreserve(device,'recovery')
            lock.release()

    def loop(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            while not self.stop_event.is_set():
                try:
                    online={d['SerialNumber'] for d in list_usb()}
                    with database() as db:configs=[dict(r) for r in db.execute('SELECT * FROM recovery_devices')]
                    futures=[pool.submit(self.tick_device,c,online) for c in configs]
                    for f in futures:
                        try:f.result()
                        except Exception:pass  # next bounded health cycle retries discovery
                except (OSError,DeviceError):
                    pass  # usbmux service unavailable, do not infer all devices were unplugged
                self.stop_event.wait(5)

    def start(self):
        if self.thread and self.thread.is_alive():return
        self.stop_event.clear();self.started=time.time()
        self.thread=threading.Thread(target=self.loop,daemon=True,name='phoneuse-recovery');self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=12)
        with self.guard:devices=list(self.children)
        for device in devices:self.terminate(device)


initialize()
supervisor=Supervisor()
