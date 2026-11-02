"""Nonblocking device snapshots; slow USB metadata/status probes run off the request path."""
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from .config import setting
from .usb import list_usb, device_info, wda_request

class Inventory:
    def __init__(self):
        self.guard=threading.RLock();self.items={};self.pending={};self.last_probe={};self.stop_event=threading.Event();self.thread=None
        state=Path(setting('STATE_DIR') or Path(__file__).resolve().parents[1]/'.state')
        self.path=state/'devices-cache.json'
        try:
            for item in json.loads(self.path.read_text()):
                self.items[item['id']]={**item,'online':None,'automation':'checking','detail':'Checking the device connection'}
        except (OSError,ValueError,TypeError,KeyError):pass

    def snapshot(self):
        with self.guard:return [dict(x) for x in self.items.values()]

    def probe(self, device, generation):
        ident=device['SerialNumber']
        with self.guard:old=dict(self.items.get(ident,{}))
        info={}
        if old.get('model') in (None,'Unknown','\u672a\u77e5') or time.time()-old.get('metadata_at',0)>600:
            try:info={**device_info(device),'metadata_at':time.time()}
            except Exception:pass
        try:
            status=wda_request(ident,'GET','/status',timeout=2).get('value') or {}
            health={'automation':'ready' if status.get('ready') is True else 'not_running','wda':status.get('build',{}).get('version'),'detail':''}
        except Exception:
            health={'automation':'not_running','detail':'WDA is not reachable yet; recovering'}
        with self.guard:
            current=self.items.get(ident,{})
            if current.get('usb_id')==generation and current.get('online'):
                self.items[ident]={**current,**info,**health,'checked_at':time.time()}

    def discover(self, devices, pool):
        now=time.time();online={d['SerialNumber'] for d in devices}
        with self.guard:
            for ident,item in self.items.items():
                if ident not in online:item.update(online=False,automation='offline',detail='USB disconnected; waiting to reconnect')
            for d in devices:
                ident=d['SerialNumber'];old=self.items.get(ident,{})
                self.items[ident]={**{'id':ident,'name':'iPhone','model':'Unknown','ios':'Unknown','automation':'checking'},**old,
                                  'online':True,'connection':'USB','usb_id':d['DeviceID'],'seen_at':now}
                if (not self.pending.get(ident) or self.pending[ident].done()) and now-self.last_probe.get(ident,0)>4:
                    self.last_probe[ident]=now;self.pending[ident]=pool.submit(self.probe,d,d['DeviceID'])

    def loop(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            last_save=0
            while not self.stop_event.is_set():
                try:self.discover(list_usb(),pool)
                except Exception:pass # discovery failure does not mean every device disappeared
                if time.monotonic()-last_save>10:
                    try:
                        self.path.parent.mkdir(exist_ok=True,mode=0o700)
                        temporary=self.path.with_suffix('.tmp');temporary.write_text(json.dumps(self.snapshot()));temporary.chmod(0o600);temporary.replace(self.path)
                    except OSError:pass
                    last_save=time.monotonic()
                self.stop_event.wait(2)

    def start(self):
        if self.thread and self.thread.is_alive():return
        self.stop_event.clear();self.thread=threading.Thread(target=self.loop,daemon=True,name='device-inventory');self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=6)

inventory=Inventory()
