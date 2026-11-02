"""Persistent, single-node task queue. Mutations are never replayed after restart."""
import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from . import assets, device_apps
from .service import controller, database, allowed
from .usb import DeviceError, OutcomeUnknown, wda_request

TERMINAL = {'completed', 'failed', 'partial', 'cancelled', 'interrupted', 'missed', 'unconfirmed'}


class Cancelled(Exception):
    pass


def initialize():
    with database() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS workflows(id TEXT PRIMARY KEY,owner TEXT,name TEXT,steps TEXT,updated REAL);
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,owner TEXT,kind TEXT,payload TEXT,devices TEXT,
          run_at REAL,status TEXT,results TEXT,cancel INTEGER DEFAULT 0,created REAL,updated REAL);
        ''')


def user_for(digest):
    with database() as db:
        row = db.execute('SELECT * FROM credentials WHERE hash=?', (digest,)).fetchone()
    if not row or (row['expires'] is not None and row['expires']<=time.time()):
        raise PermissionError('The API key for this job is no longer valid')
    return dict(row, devices=json.loads(row['devices']))


def public_job(row):
    item = dict(row)
    for field in ('payload', 'devices', 'results'):
        item[field] = json.loads(item[field])
    # Step content is available via the workflow endpoint, not copied into task logs.
    item['summary'] = {k: v for k, v in item['payload'].items() if k not in ('steps',)}
    item['step_count'] = len(item['payload'].get('steps', []))
    item.pop('payload'); item.pop('owner')
    return item


def get_job(owner, job_id):
    with database() as db:
        row = db.execute('SELECT * FROM jobs WHERE id=? AND owner=?', (job_id, owner['hash'])).fetchone()
    if not row:
        raise ValueError('Job not found or not accessible')
    return public_job(row)


def submit(owner, kind, devices, payload, run_at=None):
    ids = list(dict.fromkeys(devices))
    if any(not allowed(owner, d) for d in ids):
        raise PermissionError('The job includes a phone this API key cannot access')
    payload = {**payload, 'scheduled': run_at is not None}
    now = time.time(); job_id = uuid.uuid4().hex
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        pending = db.execute("SELECT COUNT(*) FROM jobs WHERE owner=? AND status IN ('queued','running','cancelling')", (owner['hash'],)).fetchone()[0]
        if pending >= 20:
            raise ValueError('Too many pending jobs (maximum 20)')
        if 'asset_id' in payload:
            row = db.execute('SELECT kind,metadata FROM assets WHERE id=? AND owner=?', (payload['asset_id'], owner['hash'])).fetchone()
            if not row or (kind == 'install' and row['kind'] != 'ipa') or (kind == 'media' and row['kind'] not in ('photo', 'video')):
                raise ValueError('The file type does not match, or the file is not accessible')
            if kind == 'install' and json.loads(row['metadata'])['bundle_id'] == assets.RUNNER:
                raise ValueError('A job cannot replace the WebDriverAgent app that controls the phone')
        db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                   (job_id, owner['hash'], kind, json.dumps(payload), json.dumps(ids), run_at or now,
                    'queued', '{}', 0, now, now))
    return get_job(owner, job_id)


def cancel(owner, job_id):
    get_job(owner, job_id)
    with database() as db:
        db.execute("UPDATE jobs SET cancel=1,status=CASE WHEN status='queued' THEN 'cancelled' ELSE 'cancelling' END,updated=? WHERE id=? AND owner=? AND status IN ('queued','running','cancelling')", (time.time(), job_id, owner['hash']))
    return get_job(owner, job_id)


class Scheduler:
    def __init__(self):
        self.stop_event = threading.Event()
        self.thread = None
        self.result_lock = threading.Lock()

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        with database() as db:
            db.execute("UPDATE jobs SET status='interrupted',updated=? WHERE status IN ('running','cancelling')", (time.time(),))
            db.execute("UPDATE jobs SET status='missed',updated=? WHERE status='queued' AND run_at<?", (time.time(), time.time()-300))
        self.stop_event.clear()
        self.thread = threading.Thread(target=self.loop, daemon=True, name='phoneuse-scheduler')
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=2)

    def loop(self):
        while not self.stop_event.is_set():
            try:
                with database() as db:
                    row = db.execute("SELECT id FROM jobs WHERE status='queued' AND run_at<=? ORDER BY run_at,created LIMIT 1", (time.time(),)).fetchone()
                if row:
                    self.run_job(row['id'])
                else:
                    self.stop_event.wait(.5)
            except Exception:
                self.stop_event.wait(1)

    def update_result(self, job_id, device, **values):
        with self.result_lock, database() as db:
            row = db.execute('SELECT results FROM jobs WHERE id=?', (job_id,)).fetchone()
            results = json.loads(row['results'])
            results[device] = {**results.get(device, {}), **values}
            db.execute('UPDATE jobs SET results=?,updated=? WHERE id=?', (json.dumps(results), time.time(), job_id))

    def check(self, job_id, digest, device):
        if self.stop_event.is_set():
            raise Cancelled('The local API stopped; the job did not continue')
        with database() as db:
            row = db.execute('SELECT cancel FROM jobs WHERE id=?', (job_id,)).fetchone()
        if not row or row['cancel']:
            raise Cancelled('Stopped. Actions already sent to the phone are not undone')
        user = user_for(digest)
        controller.check_lease(user, device)
        return user

    def wait(self, seconds, job_id, digest, device):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.check(job_id, digest, device)
            self.stop_event.wait(min(.25, end - time.monotonic()))

    def execute_device(self, job, device):
        job_id, digest = job['id'], job['owner']
        payload = json.loads(job['payload']); owned_before = False; reserved = False; acquired = False
        completed = 0; errors = 0; deadline = time.monotonic() + 3600
        try:
            user = user_for(digest)
            with database() as db:
                lease = db.execute('SELECT * FROM leases WHERE device=? AND expires>?', (device, time.time())).fetchone()
                owned_before = bool(lease and lease['owner'] == digest)
            controller.reserve(device, job_id); reserved = True
            # Scheduled tasks acquire only free or same-owner devices, never another user's lease.
            controller.acquire(user, device, 900); acquired = True
            self.update_result(job_id, device, status='running', completed=0, percent=0)
            if job['kind'] == 'workflow':
                steps = payload['steps']; total = len(steps) * payload.get('repeat', 1)
                for cycle in range(payload.get('repeat', 1)):
                    for index, step in enumerate(steps):
                        if time.monotonic() > deadline:
                            raise DeviceError('The job reached its one-hour limit')
                        user = self.check(job_id, digest, device)
                        controller.acquire(user, device, 900)
                        self.update_result(job_id, device, cycle=cycle + 1, step=index + 1, total=total)
                        self.wait(step['wait_ms'] / 1000, job_id, digest, device)
                        user = self.check(job_id, digest, device)
                        try:
                            c = step['command']
                            controller.perform(user, device, c['action'], c, job=job_id)
                        except DeviceError as exc:
                            errors += 1
                            self.update_result(job_id, device, errors=errors, last_error=str(exc)[:200])
                            if payload.get('on_error', 'stop') == 'stop':
                                raise
                        completed += 1
                        self.update_result(job_id, device, completed=completed, percent=round(completed * 100 / total))
                    if cycle + 1 < payload.get('repeat', 1):
                        self.wait(payload.get('interval_ms', 0) / 1000, job_id, digest, device)
            else:
                self.check(job_id, digest, device)
                with controller.lock(device):
                    user = self.check(job_id, digest, device)
                    def progress(value, *args):
                        self.update_result(job_id, device, percent=min(99, max(0, int(value))))
                    success = False
                    try:
                        if job['kind'] == 'uninstall':
                            device_apps.operate(device, 'uninstall', payload['bundle_id'], progress)
                        else:
                            asset = assets.get_asset(user, payload['asset_id'])
                            path = assets.asset_path(asset['id'])
                            if job['kind'] == 'install':
                                device_apps.operate(device, 'install', path, progress)
                            else:
                                route = '/wda/importPhoto' if asset['kind'] == 'photo' else '/wda/importVideo'
                                wda_request(device, 'POST', route, path.read_bytes(), binary=True,
                                            content_type=asset['metadata']['mime'], timeout=120)
                        success = True
                    finally:
                        with database() as db:
                            db.execute('INSERT INTO audit(time,owner,device,action,success,error) VALUES (?,?,?,?,?,?)',
                                       (time.time(), digest, device, job['kind'], int(success), None if success else 'Job failed. Check the job status; do not retry automatically'))
                completed = 1
                self.update_result(job_id, device, completed=1, percent=100)
            self.check(job_id, digest, device)
            self.update_result(job_id, device, status='failed' if errors else 'completed', errors=errors)
        except OutcomeUnknown as exc:
            self.update_result(job_id, device, status='unconfirmed', completed=completed, error=str(exc)[:200])
        except Cancelled as exc:
            self.update_result(job_id, device, status='cancelled', completed=completed, error=str(exc))
        except Exception as exc:
            message = str(exc) if isinstance(exc, (DeviceError, PermissionError, ValueError)) else type(exc).__name__
            self.update_result(job_id, device, status='failed', completed=completed, error=message[:200])
        finally:
            try:
                if acquired and not owned_before:
                    controller.release({'hash': digest}, device, block_view=False)
            finally:
                if reserved:
                    controller.unreserve(device, job_id)

    def run_job(self, job_id):
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            job = db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
            if not job or job['status'] != 'queued' or job['run_at'] > time.time():
                return
            if json.loads(job['payload']).get('scheduled') and time.time() - job['run_at'] > 300:
                db.execute("UPDATE jobs SET status='missed',updated=? WHERE id=?", (time.time(), job_id))
                return
            db.execute("UPDATE jobs SET status='running',updated=? WHERE id=?", (time.time(), job_id))
            job = dict(job)
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda device: self.execute_device(job, device), json.loads(job['devices'])))
        with database() as db:
            row = db.execute('SELECT results,cancel FROM jobs WHERE id=?', (job_id,)).fetchone()
            statuses = [v['status'] for v in json.loads(row['results']).values()]
            status = ('interrupted' if self.stop_event.is_set() else 'cancelled' if row['cancel'] else
                      'unconfirmed' if any(s == 'unconfirmed' for s in statuses) else
                      'completed' if all(s == 'completed' for s in statuses) else
                      'partial' if any(s == 'completed' for s in statuses) else 'failed')
            db.execute('UPDATE jobs SET status=?,updated=? WHERE id=?', (status, time.time(), job_id))


initialize()
scheduler = Scheduler()
